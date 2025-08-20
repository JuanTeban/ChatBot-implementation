import logging
from pathlib import Path
from typing import List
import json

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.etl.ingest import ingest_excel_files
from app.etl.knowledge_base import build_knowledge_base
from app.etl.vectorize import vectorize_markdown_file
from app.etl.web_scraping.pipeline import run_web_scraping
from app.config.settings import (
    UPLOADS_DIR, 
    KNOWLEDGE_BASE_DIR, 
    VECTORIZATION_LOG_FILE,
    SCRAPING_LOGS_DIR,
    SCRAPING_CONFIG
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Página de administración para gestionar el ETL de datos."""
    return templates.TemplateResponse("admin.html", {"request": request})



@router.post("/upload-files")
async def upload_excel_files(files: List[UploadFile] = File(...)):
    """Sube archivos Excel a la carpeta de uploads."""
    try:
        uploaded_files = []
        
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="Archivo sin nombre detectado")
            
            if not file.filename.lower().endswith(('.xlsx', '.xls')):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Archivo {file.filename} no es un archivo Excel válido"
                )
            
            file_path = UPLOADS_DIR / file.filename
            content = await file.read()
            
            with open(file_path, 'wb') as f:
                f.write(content)
            
            uploaded_files.append({
                "filename": file.filename,
                "size": len(content),
                "path": str(file_path)
            })
            
            logger.info(f"Archivo subido: {file.filename} ({len(content)} bytes)")
        
        return JSONResponse({
            "success": True,
            "message": f"Se subieron {len(uploaded_files)} archivos correctamente",
            "files": uploaded_files
        })
        
    except Exception as e:
        logger.error(f"Error al subir archivos: {e}")
        raise HTTPException(status_code=500, detail=f"Error al subir archivos: {str(e)}")

@router.post("/run-etl")
async def run_full_etl():
    """Ejecuta el pipeline completo de ETL: ingesta → knowledge base → vectorización."""
    try:
        logger.info("Iniciando pipeline completo de ETL...")
        
        # Paso 1: Ingesta de archivos Excel
        logger.info("Paso 1/3: Ejecutando ingesta de datos...")
        ingest_result = await ingest_excel_files()
        
        if not ingest_result["success"]:
            return JSONResponse({
                "success": False,
                "step": "ingesta",
                "message": "Error durante la ingesta de datos",
                "errors": ingest_result["errors"]
            })
        
        # Paso 2: Construcción de base de conocimiento
        logger.info("Paso 2/3: Construyendo base de conocimiento...")
        kb_result = await build_knowledge_base()
        
        if not kb_result["success"]:
            return JSONResponse({
                "success": False,
                "step": "knowledge_base", 
                "message": "Error al construir base de conocimiento",
                "errors": kb_result["errors"]
            })
        
        # Paso 3: Vectorización
        logger.info("Paso 3/3: Vectorizando base de conocimiento...")
        markdown_file = Path(kb_result["markdown_file"])
        vectorize_result = await vectorize_markdown_file(markdown_file)
        
        if not vectorize_result["success"]:
            return JSONResponse({
                "success": False,
                "step": "vectorization",
                "message": "Error durante la vectorización",
                "errors": vectorize_result["errors"]
            })
        
        logger.info("Pipeline ETL completado exitosamente")
        return JSONResponse({
            "success": True,
            "message": "Pipeline ETL completado exitosamente",
            "summary": {
                "ingesta": {
                    "tablas_procesadas": ingest_result["processed_count"],
                    "tiempo": ingest_result.get("end_time")
                },
                "knowledge_base": {
                    "tablas_procesadas": kb_result["tables_processed"],
                    "archivo_markdown": kb_result["markdown_file"]
                },
                "vectorization": {
                    "tablas_vectorizadas": vectorize_result["vectorized_count"],
                    "total_tablas": vectorize_result["total_tables"]
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Error crítico en pipeline ETL: {e}")
        return JSONResponse({
            "success": False,
            "step": "pipeline",
            "message": f"Error crítico en pipeline ETL: {str(e)}"
        })

# === NUEVO: ENDPOINTS DE WEB SCRAPING ===

@router.post("/run-web-scraping")
async def run_web_scraping_endpoint():
    """Ejecuta el pipeline completo de web scraping."""
    try:
        logger.info("Iniciando pipeline de web scraping...")
        
        scraping_result = await run_web_scraping()
        
        return JSONResponse({
            "success": scraping_result["success"],
            "message": "Pipeline de web scraping completado",
            "summary": {
                "pipeline_id": scraping_result["pipeline_id"],
                "sources_processed": len(scraping_result["sources_processed"]),
                "total_scraped": scraping_result["total_scraped"],
                "total_vectorized": scraping_result["total_vectorized"],
                "errors_count": len(scraping_result["errors"]),
                "processing_time": scraping_result.get("end_time")
            },
            "details": scraping_result
        })
        
    except Exception as e:
        logger.error(f"Error en pipeline de web scraping: {e}")
        raise HTTPException(status_code=500, detail=f"Error en web scraping: {str(e)}")

@router.get("/scraping-sources")
async def get_scraping_sources():
    """Obtiene la lista de fuentes configuradas para scraping."""
    try:
        sources_info = []
        for source in SCRAPING_CONFIG["sources"]:
            sources_info.append({
                "name": source["name"],
                "domain": source["domain"],
                "urls_count": len(source["urls"]),
                "classification": source["classification"],
                "enabled": source.get("enabled", True),
                "urls": source["urls"]  # Para debugging
            })
        
        return JSONResponse({
            "success": True,
            "sources": sources_info,
            "total_sources": len(sources_info),
            "total_urls": sum(s["urls_count"] for s in sources_info)
        })
        
    except Exception as e:
        logger.error(f"Error obteniendo fuentes de scraping: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.get("/scraping-logs")
async def get_latest_scraping_logs():
    """Obtiene los logs más recientes de scraping."""
    try:
        logs = []
        
        if SCRAPING_LOGS_DIR.exists():
            log_files = sorted(
                SCRAPING_LOGS_DIR.glob("pipeline_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            # Obtener los 5 logs más recientes
            for log_file in log_files[:5]:
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                    
                    logs.append({
                        "pipeline_id": log_data.get("pipeline_id"),
                        "start_time": log_data.get("start_time"),
                        "success": log_data.get("success"),
                        "total_scraped": log_data.get("total_scraped", 0),
                        "total_vectorized": log_data.get("total_vectorized", 0),
                        "sources_count": len(log_data.get("sources_processed", [])),
                        "errors_count": len(log_data.get("errors", []))
                    })
                except Exception:
                    continue
        
        return JSONResponse({
            "success": True,
            "logs": logs,
            "logs_directory": str(SCRAPING_LOGS_DIR)
        })
        
    except Exception as e:
        logger.error(f"Error obteniendo logs de scraping: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# === ENDPOINTS EXISTENTES (sin cambios) ===

@router.post("/run-ingestion")
async def run_ingestion_only():
    """Ejecuta solo la ingesta de datos."""
    try:
        result = await ingest_excel_files()
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Error en ingesta: {e}")
        raise HTTPException(status_code=500, detail=f"Error en ingesta: {str(e)}")

@router.post("/run-knowledge-base")
async def run_knowledge_base_only():
    """Ejecuta solo la construcción de la base de conocimiento."""
    try:
        result = await build_knowledge_base()
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Error en knowledge base: {e}")
        raise HTTPException(status_code=500, detail=f"Error en knowledge base: {str(e)}")

@router.post("/run-vectorization")
async def run_vectorization_only():
    """Ejecuta solo la vectorización del último archivo de knowledge base."""
    try:
        markdown_files = list(KNOWLEDGE_BASE_DIR.glob("database_embedding_*.md"))
        if not markdown_files:
            raise HTTPException(
                status_code=404, 
                detail="No se encontraron archivos de knowledge base para vectorizar"
            )
        
        latest_file = max(markdown_files, key=lambda f: f.stat().st_mtime)
        result = await vectorize_markdown_file(latest_file)
        return JSONResponse(result)
        
    except Exception as e:
        logger.error(f"Error en vectorización: {e}")
        raise HTTPException(status_code=500, detail=f"Error en vectorización: {str(e)}")

@router.get("/status")
async def get_etl_status():
    """Obtiene el estado actual del sistema ETL."""
    try:
        excel_files_paths = list(UPLOADS_DIR.glob("*.xlsx")) + list(UPLOADS_DIR.glob("*.xls"))
        excel_files = sorted(excel_files_paths, key=lambda f: f.name)
        
        kb_files_paths = list(KNOWLEDGE_BASE_DIR.glob("database_embedding_*.md"))
        kb_files = sorted(kb_files_paths, key=lambda f: f.stat().st_mtime, reverse=True)

        vectorization_log_exists = VECTORIZATION_LOG_FILE.exists()
        
        return JSONResponse({
            "uploads": {
                "count": len(excel_files),
                "files": [f.name for f in excel_files]
            },
            "knowledge_base": {
                "count": len(kb_files),
                "latest": kb_files[0].name if kb_files else None
            },
            "vectorization_log_exists": vectorization_log_exists,
            "directories": {
                "uploads": str(UPLOADS_DIR),
                "knowledge_base": str(KNOWLEDGE_BASE_DIR),
                "scraping_logs": str(SCRAPING_LOGS_DIR)
            }
        })
        
    except Exception as e:
        logger.error(f"Error al obtener estado: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener estado: {str(e)}")

@router.get("/knowledge-base/latest-html", response_class=HTMLResponse)
async def get_latest_kb_as_html():
    """Obtiene el último archivo de knowledge base como HTML."""
    try:
        kb_files = sorted(
            list(KNOWLEDGE_BASE_DIR.glob("database_embedding_*.md")),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        if not kb_files:
            return HTMLResponse("<p>No se encontró ningún archivo de Knowledge Base.</p>", status_code=404)

        latest_file = kb_files[0]
        import markdown
        content = latest_file.read_text(encoding="utf-8")
        html = markdown.markdown(content, extensions=['tables'])
        return HTMLResponse(content=f'<div class="markdown-body">{html}</div>')

    except Exception as e:
        logger.error(f"Error al obtener KB: {e}")
        return HTMLResponse(f"<p>Error: {e}</p>", status_code=500)

@router.get("/logs/vectorization", response_class=JSONResponse)
async def get_vectorization_log():
    """Obtiene el log de la última vectorización."""
    if not VECTORIZATION_LOG_FILE.exists():
        raise HTTPException(status_code=404, detail="Log de vectorización no encontrado.")
    return JSONResponse(content=json.loads(VECTORIZATION_LOG_FILE.read_text(encoding="utf-8")))

@router.post("/upload-pdf-documents")
async def upload_pdf_documents(files: List[UploadFile] = File(...)):
    """Sube archivos PDF para procesamiento multimodal."""
    try:
        uploaded_files = []
        
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="Archivo sin nombre detectado")
            
            if not file.filename.lower().endswith('.pdf'):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Archivo {file.filename} no es un PDF válido"
                )
            
            file_path = UPLOADS_DIR / file.filename
            content = await file.read()
            
            with open(file_path, 'wb') as f:
                f.write(content)
            
            uploaded_files.append({
                "filename": file.filename,
                "size": len(content),
                "path": str(file_path)
            })
            
            logger.info(f"PDF subido: {file.filename} ({len(content)} bytes)")
        
        return JSONResponse({
            "success": True,
            "message": f"Se subieron {len(uploaded_files)} PDFs correctamente",
            "files": uploaded_files
        })
        
    except Exception as e:
        logger.error(f"Error al subir PDFs: {e}")
        raise HTTPException(status_code=500, detail=f"Error al subir PDFs: {str(e)}")

@router.post("/run-multimodal-etl")
async def run_multimodal_etl():
    """Ejecuta el pipeline multimodal completo."""
    try:
        from app.config.settings import ENABLE_MULTIMODAL
        
        if not ENABLE_MULTIMODAL:
            raise HTTPException(400, "Funcionalidad multimodal deshabilitada")
        
        logger.info("Iniciando pipeline multimodal...")
        
        # Importar y ejecutar el nuevo pipeline
        from app.etl.multimodal_ingestor import process_pdf_documents
        
        result = await process_pdf_documents()
        
        return JSONResponse({
            "success": result["success"],
            "message": "Pipeline multimodal completado",
            "summary": {
                "documentos_procesados": result.get("processed_count", 0),
                "elementos_vectorizados": result.get("vectorized_count", 0),
                "errores": len(result.get("errors", []))
            },
            "details": result
        })
        
    except Exception as e:
        logger.error(f"Error en pipeline multimodal: {e}")
        raise HTTPException(status_code=500, detail=f"Error en pipeline multimodal: {str(e)}")