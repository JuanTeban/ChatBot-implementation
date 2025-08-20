import asyncio
import chromadb
import logging
from datetime import datetime
from typing import List, Dict, Optional, Literal
from pathlib import Path
import json
import google.generativeai as genai
import re

from app.config.settings import (
    VECTOR_STORE_DIR,
    CHROMA_COLLECTIONS,
    EMBEDDING_MODEL_NAME,
    VECTORIZATION_LOG_FILE,
    GEMINI_API_KEY
)

logger = logging.getLogger(__name__)

CollectionType = Literal["schema_knowledge", "business_rules", "external_docs"]

def configure_gemini():
    """Configura la API de Gemini."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no encontrada en las variables de entorno")
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("SDK de Gemini configurado correctamente.")
    return GEMINI_API_KEY

def parse_markdown_documentation(file_path: Path) -> List[Dict[str, str]]:
    """
    Parsea el documento Markdown y lo divide en secciones, una por cada tabla.
    Utiliza un enfoque más robusto para manejar el formato.
    """
    logger.info("Parseando documentación Markdown...")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        logger.error(f"Archivo Markdown no encontrado en: {file_path}")
        return []

    # Dividir el contenido justo antes de cada cabecera de tabla, manteniendo la cabecera.
    table_sections = re.split(r'(?=### TABLE \d+:)', content)
    
    if len(table_sections) < 2:
        logger.warning("No se encontraron secciones de tabla con el formato '### TABLE ...' en el archivo.")
        return []

    parsed_tables = []
    for section in table_sections[1:]:
        section_content = section.strip()
        
        # Extraer el nombre de la tabla de la primera línea para los metadatos
        first_line = section_content.split('\n', 1)[0]
        match = re.search(r'### TABLE \d+: (.+)', first_line)
        
        if match:
            table_name = match.group(1).strip()
            clean_content = section_content.removesuffix('---').strip()

            parsed_tables.append({
                'table_name': table_name,
                'content': clean_content
            })
            logger.info(f"Tabla parseada: '{table_name}' ({len(clean_content)} caracteres)")
        else:
            logger.warning(f"No se pudo extraer el nombre de la tabla de la sección: {first_line}")

    logger.info(f"Parseado completado. {len(parsed_tables)} tablas encontradas.")
    return parsed_tables

def save_log(log_data: Dict, collection_type: CollectionType):
    """Guarda el log de vectorización específico por colección."""
    try:
        # Log específico por colección
        collection_log_file = VECTORIZATION_LOG_FILE.parent / f"vectorization_{collection_type}_log.json"
        
        with open(collection_log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Log guardado en: {collection_log_file}")
        
        # También actualizar el log general
        with open(VECTORIZATION_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Error al guardar log: {e}")

async def vectorize_to_collection(
    documents: List[Dict[str, str]], 
    collection_type: CollectionType,
    clear_collection: bool = True
) -> Dict[str, any]:
    """
    Vectoriza documentos a una colección específica.
    
    Args:
        documents: Lista de documentos con 'content' y metadatos
        collection_type: Tipo de colección ("schema_knowledge", "business_rules", "external_docs")
        clear_collection: Si debe vaciar la colección antes de cargar
        
    Returns:
        Dict con el resultado del proceso
    """
    result = {
        "success": True,
        "collection_type": collection_type,
        "vectorized_count": 0,
        "total_documents": len(documents),
        "errors": [],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    # Inicializar log
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'collection_type': collection_type,
        'collection_name': CHROMA_COLLECTIONS[collection_type],
        'chroma_path': str(VECTOR_STORE_DIR),
        'validation': {'success': True},
        'parsing': {'total_documents': len(documents), 'documents': []},
        'vectorization': {'total_documents': len(documents), 'successful': 0, 'errors': [], 'details': []}
    }
    
    logger.info(f"🚀 Iniciando vectorización a colección '{collection_type}'...")
    
    try:
        # Configurar Gemini
        try:
            configure_gemini()
        except ValueError as e:
            error_msg = str(e)
            result["errors"].append(error_msg)
            result["success"] = False
            log_data['validation']['success'] = False
            log_data['validation']['error'] = error_msg
            save_log(log_data, collection_type)
            return result
        
        # Validar documentos
        if not documents:
            error_msg = f"No hay documentos para vectorizar en '{collection_type}'"
            result["errors"].append(error_msg)
            result["success"] = False
            log_data['validation']['success'] = False
            log_data['validation']['error'] = error_msg
            save_log(log_data, collection_type)
            return result
        
        # Preparar metadatos de log
        log_data['parsing']['documents'] = [
            {
                'document_id': doc.get('table_name', doc.get('source_id', f'doc_{i}')),
                'content_length': len(doc.get('content', '')),
            } for i, doc in enumerate(documents)
        ]
        
        # Inicializar ChromaDB
        logger.info(f"📚 Inicializando ChromaDB para '{collection_type}'...")
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        
        collection_name = CHROMA_COLLECTIONS[collection_type]
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={
                "description": f"Colección {collection_type}",
                "domain": collection_type,
                "created_at": datetime.now().isoformat()
            }
        )

        # CRÍTICO: Solo vaciar ESTA colección específica si se solicita
        if clear_collection:
            try:
                count = collection.count()
                if count > 0:
                    logger.info(f"🧹 Colección '{collection_name}' tiene {count} elementos. Vaciando...")
                    ids_to_delete = collection.get(include=[])['ids']
                    if ids_to_delete:
                        collection.delete(ids=ids_to_delete)
                    logger.info(f"✅ Colección '{collection_name}' vaciada exitosamente.")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo vaciar colección '{collection_name}': {e}")
        
        # Vectorizar cada documento
        logger.info(f"⚙️ Iniciando vectorización de {len(documents)} documentos...")
        vectorized_count = 0
        errors = []
        
        log_data['vectorization']['total_documents'] = len(documents)
        
        for i, doc in enumerate(documents, 1):
            doc_id = doc.get('table_name', doc.get('source_id', f'doc_{collection_type}_{i}'))
            content = doc.get('content', '')
            
            try:
                start_time = datetime.now()
                logger.info(f"[{i}/{len(documents)}] Vectorizando: {doc_id}")
                
                # Generar embedding con Gemini
                logger.debug(f"Generando embedding con Gemini...")
                embedding = await asyncio.to_thread(
                    genai.embed_content,
                    model=EMBEDDING_MODEL_NAME,
                    content=content,
                    task_type="RETRIEVAL_DOCUMENT"
                )
                embedding = embedding["embedding"]
                
                embedding_size = len(embedding)
                logger.debug(f"Embedding generado ({embedding_size} dimensiones)")
                
                # Preparar metadatos específicos por tipo
                metadata = {
                    'collection_type': collection_type,
                    'content_length': len(content),
                    'embedding_size': embedding_size,
                    'created_at': datetime.now().isoformat(),
                    **doc  # Incluir metadatos específicos del documento
                }
                
                # Añadir a ChromaDB
                logger.debug(f"Guardando en ChromaDB...")
                await asyncio.to_thread(
                    collection.add,
                    embeddings=[embedding],
                    documents=[content],
                    ids=[doc_id],
                    metadatas=[metadata]
                )
                
                processing_time = (datetime.now() - start_time).total_seconds()
                vectorized_count += 1
                
                logger.info(f"[{i}/{len(documents)}] ✅ {doc_id} vectorizado exitosamente ({processing_time:.2f}s)")
                
                # Guardar detalles en log
                log_data['vectorization']['details'].append({
                    'document_id': doc_id,
                    'status': 'success',
                    'processing_time': processing_time,
                    'embedding_size': embedding_size
                })
                
            except Exception as e:
                error_msg = f"Error vectorizando {doc_id}: {e}"
                logger.error(f"[{i}/{len(documents)}] ❌ {error_msg}")
                errors.append(error_msg)
                
                # Guardar error en log
                log_data['vectorization']['details'].append({
                    'document_id': doc_id,
                    'status': 'error',
                    'error_message': str(e),
                })
        
        # Actualizar resultados
        result["vectorized_count"] = vectorized_count
        result["errors"] = errors
        
        if errors:
            result["success"] = False
        
        # Actualizar log final
        log_data['vectorization']['successful'] = vectorized_count
        log_data['vectorization']['errors'] = errors
        log_data['vectorization']['completion_time'] = datetime.now().isoformat()
        
        # Resumen final
        logger.info("="*80)
        logger.info(f"VECTORIZACIÓN '{collection_type}' COMPLETADA")
        logger.info("="*80)
        logger.info(f"✅ Documentos vectorizados: {vectorized_count}/{len(documents)}")
        logger.info(f"❌ Errores: {len(errors)}")
        logger.info(f"📁 Colección: {collection_name}")
        
        if errors:
            logger.error("Errores encontrados:")
            for error in errors:
                logger.error(f"  - {error}")
        
    except Exception as e:
        error_msg = f"Error crítico durante vectorización '{collection_type}': {e}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["success"] = False
        log_data['vectorization']['errors'].append(error_msg)
        
    finally:
        result["end_time"] = datetime.now().isoformat()
        save_log(log_data, collection_type)
    
    return result

# MANTENER COMPATIBILIDAD: Función para esquema (ETL actual)
async def vectorize_markdown_file(markdown_file_path: Path) -> Dict[str, any]:
    """
    Vectoriza el contenido del archivo Markdown de esquema a schema_knowledge.
    Mantiene compatibilidad con el ETL actual.
    """
    logger.info("🔄 [COMPATIBILIDAD] Vectorizando archivo Markdown de esquema...")
    
    # Parsear documentación de esquema
    table_docs = await asyncio.to_thread(parse_markdown_documentation, markdown_file_path)
    
    if not table_docs:
        return {
            "success": False,
            "errors": ["No se pudieron parsear documentos del archivo Markdown"],
            "vectorized_count": 0,
            "total_tables": 0
        }
    
    # Vectorizar a schema_knowledge
    result = await vectorize_to_collection(
        documents=table_docs,
        collection_type="schema_knowledge",
        clear_collection=True  # Mantener comportamiento actual
    )
    
    # Adaptar respuesta para compatibilidad
    result["total_tables"] = result.get("total_documents", 0)
    
    return result

# NUEVO: Función helper para multimodal
async def vectorize_multimodal_documents(documents: List[Dict[str, str]]) -> Dict[str, any]:
    """
    Vectoriza documentos multimodales a external_docs.
    Wrapper que reutiliza la función existente.
    """
    logger.info("🔄 [MULTIMODAL] Vectorizando documentos multimodales...")
    
    return await vectorize_to_collection(
        documents=documents,
        collection_type="external_docs",
        clear_collection=False  # No limpiar, solo añadir
    )
