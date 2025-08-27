import logging
from pathlib import Path
from typing import List
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.etl.ingest import ingest_excel_files
from app.etl.knowledge_base import build_knowledge_base
from app.etl.vectorize import vectorize_markdown_file
from app.etl.business_rules import (
    vectorize_business_rules_file,
    process_business_rules_directory,
    get_business_rules_stats,
    clear_business_rules_collection
)
from app.config.settings import (
    UPLOADS_DIR, 
    KNOWLEDGE_BASE_DIR, 
    VECTORIZATION_LOG_FILE,
    DATA_STORE_PATH
)
from app.utils.pdf_logger import pdf_logger

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

# === ENDPOINTS EXISTENTES ===

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

# === BUSINESS RULES ENDPOINTS ===

@router.post("/upload-business-rules")
async def upload_business_rules(files: List[UploadFile] = File(...)):
    """Sube archivos PDF de reglas de negocio."""
    try:
        # Crear directorio de reglas de negocio
        business_rules_dir = DATA_STORE_PATH / "business_rules"
        business_rules_dir.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = []
        
        for file in files:
            if not file.filename or not file.filename.lower().endswith('.pdf'):
                continue
                
            # Guardar archivo
            file_path = business_rules_dir / file.filename
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            uploaded_files.append({
                "filename": file.filename,
                "size": len(content),
                "path": str(file_path)
            })
            
            logger.info(f"✅ Archivo de reglas guardado: {file.filename}")
        
        if not uploaded_files:
            raise HTTPException(status_code=400, detail="No se subieron archivos PDF válidos")
        
        return {
            "success": True,
            "message": f"Se subieron {len(uploaded_files)} archivos de reglas de negocio",
            "files": uploaded_files
        }
        
    except Exception as e:
        logger.error(f"Error subiendo reglas de negocio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process-business-rules")
async def process_business_rules(
    rule_type: str,  # 'summary' o 'recommendations'
    category: str = "general"
):
    """Procesa y vectoriza las reglas de negocio subidas."""
    try:
        if rule_type not in ["summary", "recommendations"]:
            raise HTTPException(
                status_code=400, 
                detail="rule_type debe ser 'summary' o 'recommendations'"
            )
        
        business_rules_dir = DATA_STORE_PATH / "business_rules"
        if not business_rules_dir.exists():
            raise HTTPException(
                status_code=404, 
                detail="No se encontró directorio de reglas de negocio. Suba archivos primero."
            )
        
        logger.info(f"🔄 Iniciando procesamiento de reglas: {rule_type} - {category}")
        
        # Procesar directorio
        result = await process_business_rules_directory(
            rules_dir=business_rules_dir,
            rule_type=rule_type,
            category=category
        )
        
        if result["success"]:
            message = (
                f"✅ Procesamiento completado: {result['files_processed']} archivos, "
                f"{result['total_chunks_vectorized']} chunks vectorizados"
            )
            
            return {
                "success": True,
                "message": message,
                "details": result
            }
        else:
            return {
                "success": False,
                "message": f"❌ Procesamiento falló: {len(result['errors'])} errores",
                "errors": result["errors"],
                "details": result
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error procesando reglas de negocio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/business-rules/stats")
async def get_business_rules_statistics():
    """Obtiene estadísticas de las reglas de negocio vectorizadas."""
    try:
        stats = await get_business_rules_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de reglas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/business-rules/clear")
async def clear_business_rules():
    """Limpia completamente la colección de reglas de negocio."""
    try:
        result = await clear_business_rules_collection()
        
        if result["success"]:
            return {
                "success": True,
                "message": f"✅ Colección limpiada: {result['deleted_chunks']} chunks eliminados"
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Error desconocido"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error limpiando reglas de negocio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pdf-performance")
async def get_pdf_performance():
    """
    Endpoint para obtener métricas de rendimiento de generación de PDFs
    """
    try:
        # Obtener métricas del logger
        metrics = pdf_logger.get_metrics_summary()
        
        # Obtener estadísticas de archivos de log
        log_dir = Path("data_store/logs/pdf_flow")
        log_files = list(log_dir.glob("*.log")) if log_dir.exists() else []
        
        # Calcular estadísticas básicas de archivos
        total_logs = len(log_files)
        recent_logs = len([f for f in log_files if f.stat().st_mtime > (datetime.now() - timedelta(hours=1)).timestamp()])
        
        performance_data = {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "log_files": {
                "total": total_logs,
                "recent_1h": recent_logs,
                "log_directory": str(log_dir)
            },
            "system_status": {
                "pdf_logger_active": True,
                "log_directory_exists": log_dir.exists()
            }
        }
        
        return JSONResponse(performance_data)
        
    except Exception as e:
        logger.error(f"Error al obtener métricas de rendimiento: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.get("/pdf-performance/recent")
async def get_recent_pdf_performance():
    """
    Endpoint para obtener métricas recientes (última hora) de generación de PDFs
    """
    try:
        # Obtener métricas del logger
        metrics = pdf_logger.get_metrics_summary()
        
        # Filtrar operaciones recientes (última hora)
        cutoff_time = datetime.now() - timedelta(hours=1)
        recent_operations = {}
        
        for op_name, op_data in metrics.get("operations", {}).items():
            op_timestamp = datetime.fromisoformat(op_data["timestamp"])
            if op_timestamp > cutoff_time:
                recent_operations[op_name] = op_data
        
        recent_metrics = {
            "total_operations": len(recent_operations),
            "successful_operations": sum(1 for op in recent_operations.values() if op["success"]),
            "failed_operations": sum(1 for op in recent_operations.values() if not op["success"]),
            "average_duration": sum(op["duration"] for op in recent_operations.values()) / len(recent_operations) if recent_operations else 0,
            "operations": recent_operations
        }
        
        return JSONResponse({
            "timestamp": datetime.now().isoformat(),
            "period": "Última hora",
            "metrics": recent_metrics
        })
        
    except Exception as e:
        logger.error(f"Error al obtener métricas recientes: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.get("/pdf-performance/slowest")
async def get_slowest_pdf_operations():
    """
    Endpoint para identificar las operaciones más lentas
    """
    try:
        metrics = pdf_logger.get_metrics_summary()
        operations = metrics.get("operations", {})
        
        if not operations:
            return JSONResponse({
                "message": "No hay operaciones registradas",
                "operations": []
            })
        
        # Ordenar por duración (más lento primero)
        sorted_operations = sorted(
            operations.items(),
            key=lambda x: x[1]["duration"],
            reverse=True
        )
        
        # Tomar las 5 más lentas
        slowest_operations = sorted_operations[:5]
        
        return JSONResponse({
            "timestamp": datetime.now().isoformat(),
            "slowest_operations": [
                {
                    "operation": op_name,
                    "duration": op_data["duration"],
                    "success": op_data["success"],
                    "timestamp": op_data["timestamp"]
                }
                for op_name, op_data in slowest_operations
            ]
        })
        
    except Exception as e:
        logger.error(f"Error al obtener operaciones más lentas: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.get("/pdf-performance/errors")
async def get_pdf_errors():
    """
    Endpoint para obtener errores recientes en generación de PDFs
    """
    try:
        # Buscar errores en logs recientes
        log_dir = Path("data_store/logs/pdf_flow")
        errors = []
        
        if log_dir.exists():
            # Buscar en archivos de log de las últimas 24 horas
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            for log_file in log_dir.glob("*.log"):
                if log_file.stat().st_mtime > cutoff_time.timestamp():
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            for line_num, line in enumerate(f, 1):
                                if "❌ ERROR" in line:
                                    errors.append({
                                        "file": log_file.name,
                                        "line": line_num,
                                        "message": line.strip(),
                                        "timestamp": datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
                                    })
                    except Exception as e:
                        logger.warning(f"No se pudo leer archivo {log_file}: {e}")
        
        return JSONResponse({
            "timestamp": datetime.now().isoformat(),
            "total_errors": len(errors),
            "errors": errors[:50]  # Limitar a 50 errores
        })
        
    except Exception as e:
        logger.error(f"Error al obtener errores: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

