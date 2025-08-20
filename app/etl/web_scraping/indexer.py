"""
Indexador que procesa contenido limpio y lo prepara para vectorización.
"""
import logging
import uuid
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path

from .extractors import ContentExtractor
from .dedupe import DedupeManager
from ..vectorize import vectorize_to_collection
from app.config.settings import DOCS_TEXT_DIR, DOCS_PROCESSED_DIR

logger = logging.getLogger(__name__)

class ContentIndexer:
    """Indexa contenido scrapeado y lo vectoriza en colecciones apropiadas."""
    
    def __init__(self):
        self.extractor = ContentExtractor()
        self.dedupe_manager = DedupeManager()
    
    async def process_scraped_results(self, scraped_results: List[Dict], source_config: Dict) -> Dict[str, Any]:
        """
        Procesa resultados de scraping: extrae → deduplica → vectoriza.
        
        Args:
            scraped_results: Lista de resultados de selenium_client
            source_config: Configuración de la fuente (de SCRAPING_CONFIG)
            
        Returns:
            Dict con estadísticas del procesamiento
        """
        result = {
            "success": True,
            "source_name": source_config["name"],
            "classification": source_config["classification"],
            "total_scraped": len(scraped_results),
            "processed": 0,
            "duplicates_skipped": 0,
            "vectorized": 0,
            "errors": [],
            "processing_details": [],
            "start_time": datetime.now().isoformat()
        }
        
        logger.info(f"🔄 Procesando {len(scraped_results)} páginas scrapeadas para '{source_config['name']}'")
        
        # Paso 1: Extraer contenido limpio
        clean_documents = []
        
        for scraped_result in scraped_results:
            if not scraped_result["success"]:
                error_msg = f"Scraping falló para {scraped_result['url']}: {scraped_result.get('errors', [])}"
                result["errors"].append(error_msg)
                continue
            
            try:
                # Extraer contenido limpio
                extraction_result = self.extractor.extract_clean_content(
                    html_content=scraped_result["content"],
                    url=scraped_result["url"],
                    title=scraped_result["title"]
                )
                
                if not extraction_result["success"]:
                    error_msg = f"Extracción falló para {scraped_result['url']}"
                    result["errors"].append(error_msg)
                    continue
                
                # Verificar deduplicación
                dedupe_result = self.dedupe_manager.is_duplicate(
                    content=extraction_result["clean_text"],
                    url=scraped_result["url"]
                )
                
                if dedupe_result["is_duplicate"]:
                    result["duplicates_skipped"] += 1
                    logger.info(f"⏭️ Contenido duplicado omitido: {scraped_result['url']}")
                    continue
                
                # Registrar contenido nuevo
                content_hash = self.dedupe_manager.register_content(
                    content=extraction_result["clean_text"],
                    url=scraped_result["url"],
                    metadata={
                        "title": scraped_result["title"],
                        "extraction_method": extraction_result["metadata"]["extraction_method"],
                        "source_name": source_config["name"]
                    }
                )
                
                # Preparar documento para vectorización
                document = {
                    "content": extraction_result["clean_text"],
                    "source_id": content_hash[:16],  # ID corto para ChromaDB
                    "source_url": scraped_result["url"],
                    "title": scraped_result["title"],
                    "domain": source_config["domain"],
                    "source_name": source_config["name"],
                    "classification": source_config["classification"],
                    "content_hash": content_hash,
                    "word_count": extraction_result["extraction_stats"]["word_count"],
                    "extraction_method": extraction_result["metadata"]["extraction_method"],
                    "scraped_at": scraped_result["scraped_at"],
                    "processed_at": datetime.now().isoformat()
                }
                
                clean_documents.append(document)
                result["processed"] += 1
                
                # Guardar documento procesado para auditoría
                self._save_processed_document(document, source_config["name"])
                
                logger.info(f"✅ Documento procesado: {scraped_result['url']} ({len(extraction_result['clean_text'])} chars)")
                
            except Exception as e:
                error_msg = f"Error procesando {scraped_result['url']}: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
        
        # Paso 2: Vectorizar documentos en la colección apropiada
        if clean_documents:
            try:
                collection_type = source_config["classification"]  # "external_docs"
                
                logger.info(f"📚 Vectorizando {len(clean_documents)} documentos a colección '{collection_type}'")
                
                vectorization_result = await vectorize_to_collection(
                    documents=clean_documents,
                    collection_type=collection_type,
                    clear_collection=False  # No limpiar, solo añadir
                )
                
                if vectorization_result["success"]:
                    result["vectorized"] = vectorization_result["vectorized_count"]
                    logger.info(f"✅ Vectorización exitosa: {result['vectorized']} documentos")
                else:
                    result["errors"].extend(vectorization_result["errors"])
                    result["success"] = False
                    
            except Exception as e:
                error_msg = f"Error en vectorización: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
                result["success"] = False
        
        # Resumen final
        result["end_time"] = datetime.now().isoformat()
        
        logger.info(f"📊 Procesamiento completado:")
        logger.info(f"   - Scrapeados: {result['total_scraped']}")
        logger.info(f"   - Procesados: {result['processed']}")
        logger.info(f"   - Duplicados omitidos: {result['duplicates_skipped']}")
        logger.info(f"   - Vectorizados: {result['vectorized']}")
        logger.info(f"   - Errores: {len(result['errors'])}")
        
        return result
    
    def _save_processed_document(self, document: Dict, source_name: str):
        """Guarda documento procesado para auditoría."""
        try:
            processed_dir = DOCS_PROCESSED_DIR / source_name
            processed_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"{document['source_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            file_path = processed_dir / filename
            
            # Crear versión serializable (sin contenido completo para ahorrar espacio)
            audit_doc = {**document}
            audit_doc["content"] = document["content"][:500] + "..." if len(document["content"]) > 500 else document["content"]
            
            import json
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(audit_doc, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.warning(f"No se pudo guardar documento procesado: {e}")