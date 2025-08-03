import asyncio
import chromadb
import logging
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import json
import google.generativeai as genai
import re # Added for robust markdown parsing

from app.config.settings import (
    VECTOR_STORE_DIR,
    CHROMA_COLLECTION_NAME,
    EMBEDDING_MODEL_NAME,
    VECTORIZATION_LOG_FILE,
    GEMINI_API_KEY
)

logger = logging.getLogger(__name__)

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
    # El primer elemento de la lista será el encabezado general del documento, que ignoraremos.
    table_sections = re.split(r'(?=### TABLE \d+:)', content)
    
    if len(table_sections) < 2:
        logger.warning("No se encontraron secciones de tabla con el formato '### TABLE ...' en el archivo.")
        return []

    parsed_tables = []
    # Iteramos desde el segundo elemento (índice 1), que es la primera tabla completa.
    for section in table_sections[1:]:
        section_content = section.strip()
        
        # Extraer el nombre de la tabla de la primera línea para los metadatos
        first_line = section_content.split('\n', 1)[0]
        match = re.search(r'### TABLE \d+: (.+)', first_line)
        
        if match:
            table_name = match.group(1).strip()
            
            # El contenido es la sección completa. Limpiamos el separador "---" al final.
            clean_content = section_content.removesuffix('---').strip()

            parsed_tables.append({
                'table_name': table_name,
                'content': clean_content
            })
            logger.info(f"Tabla parseada: '{table_name}' ({len(clean_content)} caracteres)")
        else:
            logger.warning(f"No se pudo extraer el nombre de la tabla de la sección: {first_line}")

    if not parsed_tables:
        logger.warning("El parseo no encontró tablas válidas a pesar de encontrar secciones.")

    logger.info(f"Parseado completado. {len(parsed_tables)} tablas encontradas.")
    return parsed_tables


def save_log(log_data: Dict):
    """Guarda el log de vectorización en un archivo JSON."""
    try:
        with open(VECTORIZATION_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Log guardado en: {VECTORIZATION_LOG_FILE}")
    except Exception as e:
        logger.error(f"Error al guardar log: {e}")

async def vectorize_markdown_file(markdown_file_path: Path) -> Dict[str, any]:
    """
    Vectoriza el contenido del archivo Markdown y lo almacena en ChromaDB.
    
    Args:
        markdown_file_path: Ruta al archivo Markdown generado
        
    Returns:
        Dict con el resultado del proceso
    """
    result = {
        "success": True,
        "vectorized_count": 0,
        "total_tables": 0,
        "errors": [],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    # Inicializar log
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'markdown_file': str(markdown_file_path),
        'chroma_path': str(VECTOR_STORE_DIR),
        'collection_name': CHROMA_COLLECTION_NAME,
        'validation': {'success': True},
        'parsing': {'total_tables': 0, 'tables': []},
        'vectorization': {'total_tables': 0, 'successful': 0, 'errors': [], 'details': []}
    }
    
    logger.info("Iniciando proceso de vectorización...")
    
    try:
        # Validar archivo Markdown
        if not markdown_file_path.exists() or not markdown_file_path.is_file():
            error_msg = "Archivo Markdown no encontrado o formato incorrecto"
            result["errors"].append(error_msg)
            result["success"] = False
            log_data['validation']['success'] = False
            log_data['validation']['error'] = error_msg
            save_log(log_data)
            return result
        
        # Configurar Gemini
        try:
            configure_gemini()
        except ValueError as e:
            error_msg = str(e)
            result["errors"].append(error_msg)
            result["success"] = False
            log_data['validation']['success'] = False
            log_data['validation']['error'] = error_msg
            save_log(log_data)
            return result
        
        # Parsear documentación
        logger.info("Parseando documentación Markdown...")
        table_docs = await asyncio.to_thread(parse_markdown_documentation, markdown_file_path)
        
        result["total_tables"] = len(table_docs)
        log_data['parsing']['total_tables'] = len(table_docs)
        log_data['parsing']['tables'] = [
            {
                'table_name': doc['table_name'],
                'content_length': len(doc['content']),
            } for doc in table_docs
        ]
        
        # Inicializar ChromaDB
        logger.info("Inicializando ChromaDB...")
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        
        # --- CORRECCIÓN: Se usa un método más robusto para reiniciar la colección ---
        # El método get_or_create_collection es la forma más segura de manejar esto.
        # Funciona tanto si la colección existe como si no (por ejemplo, si la borraste manualmente).
        collection = chroma_client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"description": "SQL Knowledge Base for Text-to-SQL queries"}
        )

        # Ahora, en lugar de borrar la colección, simplemente vaciamos su contenido si es necesario.
        # Esto es más seguro y evita errores.
        try:
            # Obtenemos la cantidad de elementos.
            count = collection.count()
            if count > 0:
                logger.info(f"Colección existente '{CHROMA_COLLECTION_NAME}' encontrada con {count} elementos. Vaciando contenido...")
                # Para vaciar la colección, obtenemos todos los IDs y los borramos.
                ids_to_delete = collection.get(include=[])['ids'] # Solo necesitamos los IDs
                if ids_to_delete:
                    collection.delete(ids=ids_to_delete)
                logger.info("Contenido anterior eliminado exitosamente.")
        except Exception as e:
            logger.warning(f"No se pudo verificar o limpiar la colección (esto puede ser un error menor, el proceso continuará): {e}")
        
        # Vectorizar cada tabla
        logger.info("Iniciando vectorización de tablas...")
        vectorized_count = 0
        errors = []
        
        log_data['vectorization']['total_tables'] = len(table_docs)
        
        for i, doc in enumerate(table_docs, 1):
            table_name = doc['table_name']
            text_context = doc['content']
            
            try:
                start_time = datetime.now()
                logger.info(f"[{i}/{len(table_docs)}] Vectorizando: {table_name}")
                
                # Generar embedding con Gemini
                logger.debug(f"Generando embedding con Gemini...")
                embedding = await asyncio.to_thread(
                    genai.embed_content,
                    model=EMBEDDING_MODEL_NAME,
                    content=text_context,
                    task_type="RETRIEVAL_DOCUMENT"
                )
                embedding = embedding["embedding"]
                
                embedding_size = len(embedding)
                logger.debug(f"Embedding generado ({embedding_size} dimensiones)")
                
                # Añadir a ChromaDB
                logger.debug(f"Guardando en ChromaDB...")
                await asyncio.to_thread(
                    collection.add,
                    embeddings=[embedding],
                    documents=[text_context],
                    ids=[table_name],
                    metadatas=[{
                        'table_name': table_name,
                        'content_length': len(text_context),
                        'embedding_size': embedding_size,
                        'created_at': datetime.now().isoformat()
                    }]
                )
                
                processing_time = (datetime.now() - start_time).total_seconds()
                vectorized_count += 1
                
                logger.info(f"[{i}/{len(table_docs)}] ✓ {table_name} vectorizado exitosamente ({processing_time:.2f}s)")
                
                # Guardar detalles en log
                log_data['vectorization']['details'].append({
                    'table_name': table_name,
                    'status': 'success',
                    'processing_time': processing_time,
                    'embedding_size': embedding_size
                })
                
            except Exception as e:
                error_msg = f"Error vectorizando {table_name}: {e}"
                logger.error(f"[{i}/{len(table_docs)}] ✗ {error_msg}")
                errors.append(error_msg)
                
                # Guardar error en log
                log_data['vectorization']['details'].append({
                    'table_name': table_name,
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
        logger.info("VECTORIZACIÓN COMPLETADA")
        logger.info("="*80)
        logger.info(f"✓ Tablas vectorizadas exitosamente: {vectorized_count}/{len(table_docs)}")
        logger.info(f"✗ Errores: {len(errors)}")
        logger.info(f"📁 Base de datos de vectores: {VECTOR_STORE_DIR}")
        logger.info(f"📝 Log detallado: {VECTORIZATION_LOG_FILE}")
        
        if errors:
            logger.error("Errores encontrados:")
            for error in errors:
                logger.error(f"  - {error}")
        
    except Exception as e:
        error_msg = f"Error crítico durante vectorización: {e}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["success"] = False
        log_data['vectorization']['errors'].append(error_msg)
        
    finally:
        result["end_time"] = datetime.now().isoformat()
        save_log(log_data)
    
    return result
