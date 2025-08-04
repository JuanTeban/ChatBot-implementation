import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import json

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.etl.ingest import ingest_excel_files
from app.etl.knowledge_base import build_knowledge_base
from app.etl.vectorize import vectorize_markdown_file
from app.config.settings import UPLOADS_DIR, KNOWLEDGE_BASE_DIR, VECTORIZATION_LOG_FILE, LOGS_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Página de administración para gestionar el ETL de datos."""
    return templates.TemplateResponse("admin.html", {"request": request})

@router.get("/chat-ui", response_class=RedirectResponse)
async def redirect_to_chat():
    """Redirige al chat UI."""
    return RedirectResponse(url="/chat-ui")

@router.post("/upload-files")
async def upload_excel_files(files: List[UploadFile] = File(...)):
    """
    Sube archivos Excel a la carpeta de uploads.
    """
    try:
        uploaded_files = []
        
        for file in files:
            # Validar que el archivo tiene nombre
            if not file.filename:
                raise HTTPException(status_code=400, detail="Archivo sin nombre detectado")
            
            if not file.filename.lower().endswith(('.xlsx', '.xls')):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Archivo {file.filename} no es un archivo Excel válido"
                )
            
            # Guardar archivo
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
    """
    Ejecuta el pipeline completo de ETL: ingesta → knowledge base → vectorización.
    """
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
        
        # Resultado exitoso
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
        # Buscar el archivo markdown más reciente
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
        # Contar y ordenar archivos en uploads
        excel_files_paths = list(UPLOADS_DIR.glob("*.xlsx")) + list(UPLOADS_DIR.glob("*.xls"))
        excel_files = sorted(excel_files_paths, key=lambda f: f.name)
        
        # Contar y ordenar archivos de knowledge base
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
                "knowledge_base": str(KNOWLEDGE_BASE_DIR)
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