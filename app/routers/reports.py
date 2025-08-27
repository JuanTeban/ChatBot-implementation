import json
import uuid
import logging
from typing import Dict, Any, List, Optional
import os
import sys
import asyncio
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from app.report_generator.engine_preview import (
    generate_report_preview,
    generate_report_from_template,
)
from app.tools.tools import execute_duckdb_query
from app.report_generator.sql_registry import (
    save_preview,
    activate_template_from_preview,
    get_active_template,
)
from app.email_sender.sender import email_sender
from app.utils.pdf_logger import pdf_logger


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])
templates = Jinja2Templates(directory="templates")

PREVIEWS: Dict[str, Dict[str, Any]] = {}

def _duck_to_json_rows(raw: str) -> List[Dict[str, Any]]:
    try:
        obj = json.loads(raw or "{}")
        if "SQL_ERROR" in (obj.get("table_str") or ""):
            raise RuntimeError(obj.get("table_str"))
        return obj.get("json_data") or []
    except Exception as e:
        raise RuntimeError(f"execute_duckdb_query: salida inválida: {e}")

@router.get("/responsables.json")
async def responsables_json():
    """Lista de responsables (para autocompletar)."""
    sql = """
    SELECT DISTINCT responsable_del_defecto AS responsable
    FROM seguimiento_hallazgos_solman_seguimiento_detalles_defecto
    WHERE responsable_del_defecto IS NOT NULL
      AND LENGTH(TRIM(responsable_del_defecto)) > 0
    ORDER BY 1;
    """
    rows = _duck_to_json_rows(execute_duckdb_query.invoke({"sql_query": sql}))
    return JSONResponse([r["responsable"] for r in rows if r.get("responsable")])

@router.get("/preview", response_class=HTMLResponse)
async def preview_form(request: Request, q: Optional[str] = None):
    """Página con formulario + vista previa (si q)."""
    return templates.TemplateResponse(
        "report_preview.html",
        {"request": request, "preview": None, "q": q}
    )

@router.post("/preview", response_class=HTMLResponse)
async def preview_generate(request: Request, responsable: str = Form(...)):
    """Genera la vista previa SOLO para un responsable."""
    responsable = (responsable or "").strip()
    if not responsable:
        raise HTTPException(status_code=400, detail="Responsable vacío.")

    preview = await generate_report_preview(responsable)
    preview_id = str(uuid.uuid4())
    PREVIEWS[preview_id] = preview

    try:
        save_preview(preview_id, preview)
        logger.info(f"[reports] Preview {preview_id} persistida en registry.")
    except Exception as e:
        logger.exception(f"[reports] No se pudo persistir preview {preview_id}: {e}")

    return templates.TemplateResponse(
        "report_preview.html",
        {"request": request, "preview": {"id": preview_id, **preview}, "q": responsable}
    )

@router.get("/preview/{preview_id}", response_class=HTMLResponse)
async def preview_view(request: Request, preview_id: str):
    preview = PREVIEWS.get(preview_id)
    if not preview:
        raise HTTPException(status_code=404, detail="Preview no encontrado.")
    return templates.TemplateResponse(
        "report_preview.html",
        {"request": request, "preview": {"id": preview_id, **preview}, "q": preview.get("preview_for")}
    )

@router.post("/preview/{preview_id}/approve")
async def preview_approve(preview_id: str):
    """
    Marca la vista previa como 'aprobada' y activa su SQL plantilla
    para correr lotes (batch) sin volver a pedir LLM-SQL.
    """
    if preview_id not in PREVIEWS:
        # igual intentamos si está persistida
        ok = activate_template_from_preview(preview_id, author="api")
        if ok != "ok":
            raise HTTPException(status_code=404, detail="Preview no encontrado.")
        logger.info(f"[reports] (persistido) Preview {preview_id} aprobado y activado.")
        return RedirectResponse(url=f"/reports/preview/{preview_id}", status_code=303)

    # guardar y activar a partir de la memoria
    save_preview(preview_id, PREVIEWS[preview_id])
    ok = activate_template_from_preview(preview_id, author="api")
    if ok != "ok":
        raise HTTPException(status_code=500, detail="No fue posible activar la plantilla.")
    logger.info(f"[reports] Preview {preview_id} aprobado y activado.")
    return RedirectResponse(url=f"/reports/preview/{preview_id}", status_code=303)

@router.get("/render_from_template/{preview_id}", response_class=HTMLResponse)
async def render_from_template(request: Request, preview_id: str, responsable: str = Query(...)):
    """
    Renderiza un reporte usando la SQL plantilla de un preview aprobado.
    Si el preview no está en memoria, toma la versión persistida (activa).
    """
    # 1) intentar en memoria
    tpl: Optional[str] = None
    pv = PREVIEWS.get(preview_id)
    if pv:
        tpl = pv["sections"]["summary"]["sql_template"]

    # 2) si no está, usa la plantilla activa en disco
    if not tpl:
        tpl = get_active_template()
    if not tpl:
        raise HTTPException(status_code=404, detail="No hay plantilla activa disponible.")

    rep = await generate_report_from_template(responsable, tpl)
    # no cambiamos el preview_id, solo renderizamos para este responsable
    return templates.TemplateResponse(
        "report_preview.html",
        {"request": request, "preview": {"id": preview_id, **rep}, "q": responsable}
    )

@router.get("/render_active", response_class=HTMLResponse)
async def render_active(request: Request, responsable: str = Query(...)):
    """
    Renderiza un reporte usando SIEMPRE la plantilla activa global.
    Conveniente para el exportador por lote.
    """
    tpl = get_active_template()
    if not tpl:
        raise HTTPException(status_code=404, detail="No hay plantilla activa disponible.")
    rep = await generate_report_from_template(responsable, tpl)
    return templates.TemplateResponse(
        "report_preview.html",
        {"request": request, "preview": {"id": "active", **rep}, "q": responsable}
    )


@router.get("/pdf/{preview_id}", response_class=FileResponse)
async def pdf_preview(preview_id: str):
    """
    Descarga la VISTA PREVIA (exactamente esa), renderizada como PDF.
    No cambiamos el event loop de la app: levantamos un subproceso Python.
    """
    # Confirmamos que existe en memoria; si tu flujo persiste, puedes permitirlo sin este check
    if preview_id not in PREVIEWS:
        raise HTTPException(status_code=404, detail="Preview no encontrado.")

    # Obtener información del preview para logging
    preview_data = PREVIEWS[preview_id]
    consultant_name = preview_data.get("preview_for", "Consultor")
    
    # Iniciar logging detallado
    pdf_logger.log_pdf_generation_start(preview_id, consultant_name)
    
    try:
        # Paso 1: Preparar URL y directorio de salida
        pdf_logger.log_pdf_generation_step("preparar_url_y_directorio")
        base_url = os.getenv("REPORTS_BASE_URL", "http://127.0.0.1:8000")
        url = f"{base_url}/reports/preview/{preview_id}?pdf=1"
        out_dir = Path("exports")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_pdf = out_dir / f"Reporte_{preview_id}.pdf"
        pdf_logger.log_pdf_generation_step_complete("preparar_url_y_directorio", True)
        
        # Paso 2: Generar PDF con subproceso
        pdf_logger.log_pdf_generation_step("generar_pdf_subproceso", {
            "url": url,
            "output_file": str(out_pdf)
        })
        cmd = [sys.executable, "-m", "scripts.pdf_worker_url", url, str(out_pdf)]
        # Ejecutamos en hilo para no tocar el loop Proactor
        await asyncio.to_thread(subprocess.run, cmd, check=True)
        pdf_logger.log_pdf_generation_step_complete("generar_pdf_subproceso", True)

        # Paso 3: Verificar que el PDF se generó
        if not out_pdf.exists():
            pdf_logger.log_error("verificar_pdf", Exception("PDF no encontrado después de generación"))
            raise HTTPException(status_code=500, detail="No se generó el PDF")
        
        pdf_logger.log_pdf_generation_step_complete("verificar_pdf", True)
        
        # Paso 4: Envío automático de correo
        pdf_logger.log_email_sending_start("test_recipient", str(out_pdf))
        
        try:
            # Obtener información del preview para el correo
            consultant_name = preview_data.get("preview_for", "Consultor")
            
            # Enviar correo automáticamente
            email_success = await asyncio.to_thread(
                email_sender.send_report_email,
                pdf_path=str(out_pdf),
                consultant_name=consultant_name,
                report_id=preview_id
            )
            
            if email_success:
                pdf_logger.log_email_complete(True)
                logger.info(f"✅ Correo enviado automáticamente para preview {preview_id}")
            else:
                pdf_logger.log_email_complete(False)
                logger.warning(f"⚠️ No se pudo enviar el correo para preview {preview_id}")
                
        except Exception as e:
            pdf_logger.log_error("envio_email", e, {"preview_id": preview_id})
            pdf_logger.log_email_complete(False)
            logger.error(f"❌ Error al enviar correo automático: {e}")


        pdf_logger.log_pdf_generation_complete(True)
        
        return FileResponse(str(out_pdf), filename=out_pdf.name, media_type="application/pdf")
        
    except Exception as e:
        pdf_logger.log_error("generacion_pdf", e, {"preview_id": preview_id})
        pdf_logger.log_pdf_generation_complete(False)
        raise