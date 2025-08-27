import asyncio
import chromadb
import logging
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import json
import google.generativeai as genai

from app.config.settings import (
    VECTOR_STORE_DIR,
    CHROMA_COLLECTIONS,
    EMBEDDING_MODEL_NAME,
    GEMINI_API_KEY,
    DATA_STORE_PATH
)
from app.utils.report_logger import report_flow_logger

logger = logging.getLogger(__name__)

# Directorio específico para reglas de negocio
BUSINESS_RULES_DIR = DATA_STORE_PATH / "business_rules"
BUSINESS_RULES_LOG_FILE = DATA_STORE_PATH / "logs" / "business_rules_log.json"

def configure_gemini():
    """Configura la API de Gemini."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no encontrada en las variables de entorno")
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("SDK de Gemini configurado para business rules.")
    return GEMINI_API_KEY

def get_file_hash(file_path: Path) -> str:
    """Genera hash SHA256 del archivo para detectar cambios."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extrae texto de PDF usando múltiples estrategias.
    """
    logger.info(f"Extrayendo texto de: {pdf_path.name}")
    
    try:
        # Estrategia 1: PyMuPDF (más confiable para texto)
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            text_pages = []
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text_pages.append(f"=== PÁGINA {page_num + 1} ===\n{page.get_text()}")
            doc.close()
            full_text = "\n\n".join(text_pages)
            logger.info(f"✅ PyMuPDF extrajo {len(full_text)} caracteres")
            return full_text
        except ImportError:
            logger.warning("PyMuPDF no disponible, intentando con Unstructured...")
            
        # Estrategia 2: Unstructured (fallback)
        try:
            from unstructured.partition.pdf import partition_pdf
            # Configurar para evitar warnings
            import warnings
            warnings.filterwarnings("ignore", message="No languages specified")
            
            elements = partition_pdf(str(pdf_path), strategy="auto", languages=["spa", "eng"])
            text_content = "\n\n".join([str(elem) for elem in elements])
            logger.info(f"✅ Unstructured extrajo {len(text_content)} caracteres")
            return text_content
        except ImportError:
            logger.error("Ni PyMuPDF ni Unstructured están disponibles")
            raise RuntimeError("No hay librerías disponibles para extraer PDF")
            
    except Exception as e:
        logger.error(f"Error extrayendo texto de {pdf_path.name}: {e}")
        raise

def chunk_business_rules_text(text: str, rule_type: str) -> List[Dict[str, Any]]:
    """
    Divide el texto de reglas de negocio en chunks inteligentes.
    
    Args:
        text: Texto completo extraído del PDF
        rule_type: 'summary' o 'recommendations'
    
    Returns:
        Lista de chunks con metadatos
    """
    logger.info(f"Dividiendo texto en chunks para tipo: {rule_type}")
    
    # Dividir por secciones naturales
    sections = []
    
    # Estrategia 1: Dividir por títulos/secciones
    lines = text.split('\n')
    current_section = []
    section_title = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Detectar títulos (líneas cortas, mayúsculas, con números/puntos)
        is_title = (
            len(line) < 80 and 
            (line.isupper() or 
             line.startswith(('1.', '2.', '3.', '4.', '5.')) or
             line.startswith(('I.', 'II.', 'III.', 'IV.', 'V.')) or
             'REGLA' in line.upper() or
             'PROCEDIMIENTO' in line.upper() or
             'INSTRUCCIÓN' in line.upper())
        )
        
        if is_title and current_section:
            # Guardar sección anterior
            section_content = '\n'.join(current_section)
            if len(section_content.strip()) > 50:  # Solo secciones sustanciales
                sections.append({
                    'title': section_title or 'Regla de negocio',
                    'content': section_content.strip(),
                    'type': rule_type
                })
            current_section = []
            section_title = line
        else:
            current_section.append(line)
    
    # Agregar última sección
    if current_section:
        section_content = '\n'.join(current_section)
        if len(section_content.strip()) > 50:
            sections.append({
                'title': section_title or 'Regla de negocio',
                'content': section_content.strip(),
                'type': rule_type
            })
    
    # Si no se encontraron secciones naturales, dividir por tamaño
    if not sections:
        logger.warning("No se encontraron secciones naturales, dividiendo por tamaño")
        chunk_size = 2000  # Tamaño óptimo para embeddings
        overlap = 200      # Solapamiento para mantener contexto
        
        for i in range(0, len(text), chunk_size - overlap):
            chunk_text = text[i:i + chunk_size]
            if len(chunk_text.strip()) > 100:
                sections.append({
                    'title': f'Regla de negocio - Chunk {len(sections) + 1}',
                    'content': chunk_text.strip(),
                    'type': rule_type
                })
    
    logger.info(f"✅ Creados {len(sections)} chunks para {rule_type}")
    return sections

async def vectorize_business_rules_file(
    pdf_path: Path, 
    rule_type: str,  # 'summary' o 'recommendations'
    category: str = "general"  # Para organizar mejor las reglas
) -> Dict[str, Any]:
    """
    Vectoriza un archivo PDF de reglas de negocio.
    
    Args:
        pdf_path: Ruta al PDF
        rule_type: Tipo de regla ('summary' o 'recommendations')
        category: Categoría de la regla (ej: 'kpi', 'sla', 'quality')
    
    Returns:
        Dict con resultado del proceso
    """
    result = {
        "success": True,
        "file": pdf_path.name,
        "rule_type": rule_type,
        "category": category,
        "chunks_created": 0,
        "chunks_vectorized": 0,
        "errors": [],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    logger.info(f"🔄 BUSINESS_RULES - INICIO PROCESAMIENTO")
    logger.info(f"   Archivo: {pdf_path.name}")
    logger.info(f"   Tipo: {rule_type}")
    logger.info(f"   Categoría: {category}")
    logger.info(f"   EMBEDDING_MODEL_NAME: {EMBEDDING_MODEL_NAME}")
    logger.info(f"   VECTOR_STORE_DIR: {VECTOR_STORE_DIR}")
    
    try:
        # Configurar Gemini
        logger.info(f"   Configurando Gemini...")
        configure_gemini()
        logger.info(f"   ✅ Gemini configurado")
        
        # Extraer texto del PDF
        logger.info(f"   Extrayendo texto del PDF...")
        text_content = extract_text_from_pdf(pdf_path)
        logger.info(f"   ✅ Texto extraído: {len(text_content)} caracteres")
        
        if len(text_content.strip()) < 100:
            raise ValueError("PDF contiene muy poco texto válido")
        
        # Dividir en chunks inteligentes
        logger.info(f"   Dividiendo en chunks...")
        chunks = chunk_business_rules_text(text_content, rule_type)
        result["chunks_created"] = len(chunks)
        logger.info(f"   ✅ Chunks creados: {len(chunks)}")
        
        if not chunks:
            raise ValueError("No se pudieron crear chunks válidos del PDF")
        
        # Inicializar ChromaDB
        logger.info(f"   Conectando a ChromaDB...")
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        
        # Obtener o crear colección de business rules
        collection_name = CHROMA_COLLECTIONS["business_rules"]
        logger.info(f"   Collection name: {collection_name}")
        
        try:
            logger.info(f"   Obteniendo colección existente...")
            collection = chroma_client.get_collection(name=collection_name)
            logger.info(f"   ✅ Colección obtenida")
        except Exception as e:
            logger.info(f"   ⚠️ Colección no existe, creando nueva...")
            collection = chroma_client.create_collection(
                name=collection_name,
                metadata={"description": "Business Rules for Report Generation"}
            )
            logger.info(f"   ✅ Colección creada")
        
        # Vectorizar cada chunk
        file_hash = get_file_hash(pdf_path)
        vectorized_count = 0
        
        logger.info(f"   Iniciando vectorización de {len(chunks)} chunks...")
        
        for i, chunk in enumerate(chunks):
            try:
                chunk_id = str(uuid.uuid4())
                
                # Crear contexto enriquecido para el chunk
                enriched_content = f"""TIPO: {rule_type.upper()}
CATEGORÍA: {category.upper()}
TÍTULO: {chunk['title']}

CONTENIDO:
{chunk['content']}"""
                
                # Generar embedding
                logger.info(f"   Generando embedding para chunk {i+1}/{len(chunks)}...")
                embedding_response = await asyncio.to_thread(
                    genai.embed_content,
                    model=EMBEDDING_MODEL_NAME,
                    content=enriched_content,
                    task_type="RETRIEVAL_DOCUMENT"
                )
                embedding = embedding_response["embedding"]
                logger.info(f"   ✅ Embedding generado: {len(embedding)} dimensiones")
                
                # Metadatos completos
                metadata = {
                    "chunk_id": chunk_id,
                    "source_file": pdf_path.name,
                    "file_hash": file_hash,
                    "rule_type": rule_type,
                    "category": category,
                    "title": chunk['title'],
                    "content_length": len(chunk['content']),
                    "embedding_size": len(embedding),
                    "created_at": datetime.now().isoformat(),
                    "chunk_index": i
                }
                
                # Guardar en ChromaDB
                logger.info(f"   Guardando chunk {i+1} en ChromaDB...")
                await asyncio.to_thread(
                    collection.add,
                    embeddings=[embedding],
                    documents=[enriched_content],
                    ids=[chunk_id],
                    metadatas=[metadata]
                )
                
                vectorized_count += 1
                logger.info(f"   ✅ Chunk {i+1} vectorizado: {chunk['title'][:50]}...")
                
            except Exception as e:
                error_msg = f"Error vectorizando chunk {i+1}: {e}"
                logger.error(f"   ❌ {error_msg}")
                result["errors"].append(error_msg)
        
        result["chunks_vectorized"] = vectorized_count
        
        if result["errors"]:
            result["success"] = False
        
        logger.info(f"✅ BUSINESS_RULES - PROCESAMIENTO COMPLETADO")
        logger.info(f"   Chunks vectorizados: {vectorized_count}/{len(chunks)}")
        logger.info(f"   Éxito: {result['success']}")
        
    except Exception as e:
        error_msg = f"Error crítico procesando {pdf_path.name}: {e}"
        logger.error(f"❌ BUSINESS_RULES - ERROR CRÍTICO: {error_msg}")
        result["errors"].append(error_msg)
        result["success"] = False
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
    finally:
        result["end_time"] = datetime.now().isoformat()
    
    return result

async def process_business_rules_directory(
    rules_dir: Path,
    rule_type: str,
    category: str = "general"
) -> Dict[str, Any]:
    """
    Procesa todos los PDFs en un directorio para un tipo específico de reglas.
    
    Args:
        rules_dir: Directorio con PDFs de reglas
        rule_type: 'summary' o 'recommendations' 
        category: Categoría de las reglas
    
    Returns:
        Dict con resumen del procesamiento
    """
    result = {
        "success": True,
        "rule_type": rule_type,
        "category": category,
        "files_processed": 0,
        "total_chunks_vectorized": 0,
        "errors": [],
        "files_details": [],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    logger.info(f"📁 Procesando directorio de reglas: {rules_dir} ({rule_type})")
    
    try:
        # Buscar archivos PDF
        pdf_files = [f for f in rules_dir.iterdir() if f.suffix.lower() == '.pdf']
        
        if not pdf_files:
            result["errors"].append("No se encontraron archivos PDF en el directorio")
            result["success"] = False
            return result
        
        logger.info(f"📄 Encontrados {len(pdf_files)} archivos PDF")
        
        # Procesar cada archivo
        for pdf_file in pdf_files:
            try:
                file_result = await vectorize_business_rules_file(pdf_file, rule_type, category)
                result["files_details"].append(file_result)
                result["files_processed"] += 1
                result["total_chunks_vectorized"] += file_result["chunks_vectorized"]
                
                if not file_result["success"]:
                    result["errors"].extend(file_result["errors"])
                
            except Exception as e:
                error_msg = f"Error procesando {pdf_file.name}: {e}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
        
        if result["errors"]:
            result["success"] = False
            
    except Exception as e:
        error_msg = f"Error crítico en directorio {rules_dir}: {e}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["success"] = False
        
    finally:
        result["end_time"] = datetime.now().isoformat()
    
    return result

def save_business_rules_log(log_data: Dict[str, Any]):
    """Guarda el log de procesamiento de reglas de negocio."""
    try:
        BUSINESS_RULES_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(BUSINESS_RULES_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Log guardado en: {BUSINESS_RULES_LOG_FILE}")
    except Exception as e:
        logger.error(f"Error al guardar log: {e}")

async def get_business_rules_stats() -> Dict[str, Any]:
    """
    Obtiene estadísticas de las reglas de negocio vectorizadas.
    
    Returns:
        Dict con estadísticas de la colección
    """
    try:
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        collection_name = CHROMA_COLLECTIONS["business_rules"]
        
        try:
            collection = chroma_client.get_collection(name=collection_name)
            count = collection.count()
            
            # Obtener muestra de metadatos
            sample = collection.get(include=["metadatas"], limit=100)
            metadatas = sample.get("metadatas", [])
            
            # Analizar distribución
            rule_types = {}
            categories = {}
            files = set()
            
            for meta in metadatas:
                rule_type = meta.get("rule_type", "unknown")
                category = meta.get("category", "unknown")
                source_file = meta.get("source_file", "unknown")
                
                rule_types[rule_type] = rule_types.get(rule_type, 0) + 1
                categories[category] = categories.get(category, 0) + 1
                files.add(source_file)
            
            return {
                "total_chunks": count,
                "rule_types": rule_types,
                "categories": categories,
                "source_files": list(files),
                "files_count": len(files)
            }
            
        except Exception:
            return {
                "total_chunks": 0,
                "rule_types": {},
                "categories": {},
                "source_files": [],
                "files_count": 0,
                "note": "Colección no existe aún"
            }
            
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        return {"error": str(e)}

# Función de utilidad para limpiar la colección
async def clear_business_rules_collection():
    """Limpia completamente la colección de reglas de negocio."""
    try:
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        collection_name = CHROMA_COLLECTIONS["business_rules"]
        
        try:
            collection = chroma_client.get_collection(name=collection_name)
            # Obtener todos los IDs
            all_data = collection.get(include=[])
            if all_data["ids"]:
                collection.delete(ids=all_data["ids"])
                logger.info(f"✅ Colección {collection_name} limpiada: {len(all_data['ids'])} chunks eliminados")
                return {"success": True, "deleted_chunks": len(all_data["ids"])}
            else:
                logger.info(f"Colección {collection_name} ya estaba vacía")
                return {"success": True, "deleted_chunks": 0}
                
        except Exception:
            logger.info(f"Colección {collection_name} no existe")
            return {"success": True, "deleted_chunks": 0}
            
    except Exception as e:
        logger.error(f"Error limpiando colección: {e}")
        return {"success": False, "error": str(e)}
