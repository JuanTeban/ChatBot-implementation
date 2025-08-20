"""
Pipeline principal de web scraping que orquesta todo el proceso.
"""
import logging
import asyncio
from typing import Dict, List, Any
from datetime import datetime

from .selenium_client import SeleniumClient
from .indexer import ContentIndexer
from app.config.settings import SCRAPING_CONFIG, SCRAPING_LOGS_DIR

logger = logging.getLogger(__name__)

class WebScrapingPipeline:
    """Pipeline completo de web scraping: navegación → extracción → vectorización."""
    
    def __init__(self):
        self.selenium_client = SeleniumClient()
        self.content_indexer = ContentIndexer()
    
    async def run_full_pipeline(self, source_names: List[str] = None) -> Dict[str, Any]:
        """
        Ejecuta el pipeline completo para las fuentes especificadas.
        
        Args:
            source_names: Lista de nombres de fuentes a procesar. Si None, procesa todas las activas.
            
        Returns:
            Dict con resultados del pipeline completo
        """
        pipeline_result = {
            "success": True,
            "pipeline_id": f"scraping_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "sources_processed": [],
            "total_scraped": 0,
            "total_vectorized": 0,
            "errors": [],
            "start_time": datetime.now().isoformat()
        }
        
        logger.info("🚀 Iniciando pipeline completo de web scraping")
        
        # Filtrar fuentes a procesar
        sources_to_process = []
        for source_config in SCRAPING_CONFIG["sources"]:
            if not source_config.get("enabled", True):
                continue
            
            if source_names is None or source_config["name"] in source_names:
                sources_to_process.append(source_config)
        
        if not sources_to_process:
            error_msg = "No hay fuentes activas para procesar"
            logger.warning(error_msg)
            pipeline_result["errors"].append(error_msg)
            pipeline_result["success"] = False
            return pipeline_result
        
        logger.info(f"📋 Procesando {len(sources_to_process)} fuentes: {[s['name'] for s in sources_to_process]}")
        
        # Procesar cada fuente
        for source_config in sources_to_process:
            source_result = await self._process_single_source(source_config)
            pipeline_result["sources_processed"].append(source_result)
            
            if source_result["success"]:
                pipeline_result["total_scraped"] += source_result["total_scraped"]
                pipeline_result["total_vectorized"] += source_result["vectorized"]
            else:
                pipeline_result["errors"].extend(source_result["errors"])
        
        # Determinar éxito general
        successful_sources = sum(1 for s in pipeline_result["sources_processed"] if s["success"])
        pipeline_result["success"] = successful_sources > 0 and len(pipeline_result["errors"]) == 0
        
        pipeline_result["end_time"] = datetime.now().isoformat()
        
        # Log final
        logger.info("="*80)
        logger.info("PIPELINE DE WEB SCRAPING COMPLETADO")
        logger.info("="*80)
        logger.info(f"✅ Fuentes exitosas: {successful_sources}/{len(sources_to_process)}")
        logger.info(f"📄 Total scrapeado: {pipeline_result['total_scraped']} páginas")
        logger.info(f"🔍 Total vectorizado: {pipeline_result['total_vectorized']} documentos")
        logger.info(f"❌ Errores: {len(pipeline_result['errors'])}")
        
        # Guardar log del pipeline
        self._save_pipeline_log(pipeline_result)
        
        return pipeline_result
    
    async def _process_single_source(self, source_config: Dict) -> Dict[str, Any]:
        """Procesa una fuente específica: scrapea → indexa → vectoriza."""
        source_name = source_config["name"]
        urls = source_config["urls"]
        
        logger.info(f"🎯 Procesando fuente: '{source_name}' ({len(urls)} URLs)")
        
        source_result = {
            "source_name": source_name,
            "success": False,
            "urls": urls,
            "total_scraped": 0,
            "processed": 0,
            "vectorized": 0,
            "errors": [],
            "start_time": datetime.now().isoformat()
        }
        
        try:
            # Paso 1: Scraping con Selenium
            logger.info(f"🌐 [1/2] Scrapeando {len(urls)} URLs...")
            scraped_results = self.selenium_client.scrape_multiple(urls, source_name)
            
            successful_scrapes = [r for r in scraped_results if r["success"]]
            source_result["total_scraped"] = len(successful_scrapes)
            
            if not successful_scrapes:
                error_msg = f"No se pudo scrapear ninguna URL de la fuente '{source_name}'"
                logger.error(error_msg)
                source_result["errors"].append(error_msg)
                return source_result
            
            logger.info(f"✅ Scraping completado: {len(successful_scrapes)}/{len(urls)} exitosas")
            
            # Paso 2: Procesamiento e indexación
            logger.info(f"📚 [2/2] Procesando contenido e indexando...")
            indexing_result = await self.content_indexer.process_scraped_results(
                scraped_results=successful_scrapes,
                source_config=source_config
            )
            
            # Consolidar resultados
            source_result["processed"] = indexing_result["processed"]
            source_result["vectorized"] = indexing_result["vectorized"]
            source_result["errors"].extend(indexing_result["errors"])
            
            source_result["success"] = indexing_result["success"] and source_result["vectorized"] > 0
            
            logger.info(f"✅ Fuente '{source_name}' procesada: {source_result['vectorized']} docs vectorizados")
            
        except Exception as e:
            error_msg = f"Error crítico procesando fuente '{source_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            source_result["errors"].append(error_msg)
        
        source_result["end_time"] = datetime.now().isoformat()
        return source_result
    
    def _save_pipeline_log(self, pipeline_result: Dict):
        """Guarda log detallado del pipeline."""
        try:
            log_file = SCRAPING_LOGS_DIR / f"pipeline_{pipeline_result['pipeline_id']}.json"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            import json
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(pipeline_result, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📄 Log del pipeline guardado: {log_file}")
            
        except Exception as e:
            logger.warning(f"No se pudo guardar log del pipeline: {e}")

# Función de conveniencia para usar desde admin
async def run_web_scraping(source_names: List[str] = None) -> Dict[str, Any]:
    """
    Función de conveniencia para ejecutar el pipeline desde admin o schedulers.
    
    Args:
        source_names: Lista de fuentes a procesar. Si None, procesa todas las activas.
        
    Returns:
        Resultado del pipeline
    """
    pipeline = WebScrapingPipeline()
    return await pipeline.run_full_pipeline(source_names)