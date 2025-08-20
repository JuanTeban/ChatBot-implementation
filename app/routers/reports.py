# app/routers/reports.py
import json
import uuid
import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])
templates = Jinja2Templates(directory="templates")

# memoria en proceso (útil para trabajar en caliente)
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

    preview = await generate_report_preview(responsable)   # RAG+LLM+DuckDB
    preview_id = str(uuid.uuid4())
    PREVIEWS[preview_id] = preview

    # persistimos para que no dependa de la memoria del proceso
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
