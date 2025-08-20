import json
import logging
import re
from typing import Dict, Any, List, Tuple
import pandas as pd
import asyncio

from app.agent.shared import answer_llm
from app.tools.tools import execute_duckdb_query
from .prompts import build_sql_prompt, get_prompt
from .rag import get_schema_context, get_business_snippets, join_snippets
from .contracts import (
    ensure_columns, normalize_rows, build_datacard,
    SUMMARY_REQUIRED_COLS, RECO_REQUIRED_COLS
)
from app.config.settings import ENABLE_MULTIMODAL
from .chart_builders import (
    build_aggregated_llm_chart,
    build_llm_chart,
    build_inactivity_risk_chart,
    build_effort_iterations_chart
)

log = logging.getLogger(__name__)

def _parse_tool_json(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except Exception as e:
        raise RuntimeError(f"Salida 'execute_duckdb_query' no es JSON válido: {e}")

def _extract_rows(raw: str) -> List[Dict[str, Any]]:
    obj = _parse_tool_json(raw)
    if "SQL_ERROR" in (obj.get("table_str") or ""):
        raise RuntimeError(obj.get("table_str"))
    return obj.get("json_data") or []

def _try_exec(sql: str) -> Tuple[Dict, bool]:
    raw = execute_duckdb_query.invoke({"sql_query": sql})
    obj = json.loads(raw or "{}")
    is_err = "SQL_ERROR" in (obj.get("table_str") or "")
    return obj, is_err

async def _repair_sql(question: str, sql: str, error_str: str) -> str:
    log.warning(f"Intentando reparar SQL. Error: {error_str}")
    repair_prompt_tpl = f"""Eres un experto en DuckDB. Repara la siguiente consulta SQL basándote en el error.
Devuelve SOLO el SQL, sin ```.

PREGUNTA:
{question}

ERROR:
{error_str}

SQL:
{sql}

SQL CORREGIDA:"""
    fixed_sql = (await answer_llm.ainvoke(repair_prompt_tpl)).content.strip()
    return re.sub(r"```sql|```", "", fixed_sql).rstrip(";") + ";"

def _llm_sql(question: str) -> str:
    schema_ctx = get_schema_context(question)
    prompt = build_sql_prompt(question=question, schema_context=schema_ctx)
    resp = answer_llm.invoke(prompt).content.strip()
    resp = re.sub(r"```sql|```", "", resp).strip()
    if not re.match(r"(?is)^\s*select\s", resp):
        raise RuntimeError("La SQL generada no inicia con SELECT.")
    resp = resp.rstrip(';').strip()
    return resp + ";"

async def _llm_sql_robust(question: str, max_tries: int = 3) -> str:
    sql = _llm_sql(question)
    for attempt in range(max_tries):
        obj, is_err = _try_exec(sql)
        if not is_err:
            log.info(f"SQL validada en el intento {attempt+1}.")
            return sql
        if attempt < max_tries - 1:
            sql = await _repair_sql(question, sql, obj.get("table_str", "Error desconocido."))
        else:
            raise RuntimeError(f"No fue posible generar una SQL válida: {obj.get('table_str')}")
    return sql

def _fill_template(sql_template: str, responsable: str) -> str:
    safe_responsable = responsable.replace("'", "''")
    return sql_template.replace(":RESPONSABLE", f"%{safe_responsable}%")

def _generalize_sql_for_responsable(sql: str) -> Tuple[str, str]:
    # 1) Intentar reemplazar el LIKE existente
    pat = r"(UPPER\s*\(\s*responsable_del_defecto\s*\)\s*LIKE\s*UPPER\s*\(\s*'%)([^']+)(%'\s*\))"
    repl = r"\1:RESPONSABLE\3"
    templ, n = re.subn(pat, repl, sql, flags=re.IGNORECASE)
    if n > 0:
        return templ, "usar LIKE UPPER('%<RESPONSABLE>%')"

    # 2) Fallback: parametrizar aunque no exista el filtro (envolver en subconsulta)
    log.warning("No se detectó patrón LIKE; se parametriza con subconsulta.")
    wrapped = f"SELECT * FROM ({sql.rstrip(';')}) AS T WHERE UPPER(T.responsable_del_defecto) LIKE UPPER('%:RESPONSABLE%');"
    return wrapped, "envolver como subconsulta con filtro por responsable"

def _exec_sql(sql: str) -> List[Dict[str, Any]]:
    raw = execute_duckdb_query.invoke({"sql_query": sql})
    return _extract_rows(raw)

async def generate_report_preview(consultant_name: str) -> Dict[str, Any]:
    log.info(f"Iniciando vista previa para: '{consultant_name}'")
    datacard_text = build_datacard()
    charts: Dict[str, Any] = {}

    # PASO 1 — Dataset único (SQL robusta + plantilla)
    q_full_data = (f"Para el responsable '{consultant_name}', obtener todos los campos necesarios para un reporte completo, "
                   f"incluyendo estado, bloqueante, antigüedad, módulo, defecto y comentarios.")
    sql_full_data = await _llm_sql_robust(q_full_data)
    sql_template, _ = _generalize_sql_for_responsable(sql_full_data)
    final_sql = _fill_template(sql_template, consultant_name)

    all_rows = _exec_sql(final_sql)
    all_rows = normalize_rows(all_rows)
    if not ensure_columns(all_rows, SUMMARY_REQUIRED_COLS) or not ensure_columns(all_rows, RECO_REQUIRED_COLS):
        raise RuntimeError("Dataset no cumple contrato mínimo.")

    # PASO 2 — Textos (prompts dinámicos + RAG)
    snips_summary = get_business_snippets("resumen ejecutivo defectos KPI reglas definiciones calidad")
    snips_reco = get_business_snippets("priorización plan de acción defectos reglas SLA")

    summary_tpl = get_prompt("report_summary_prompt")
    reco_tpl    = get_prompt("report_recommendations_prompt")

    summary_prompt = summary_tpl.format(
        consultant_name=consultant_name,
        data_json=json.dumps(all_rows, ensure_ascii=False, indent=2),
        snippets_text=join_snippets(snips_summary),
        datacard_text=datacard_text
    )
    reco_prompt = reco_tpl.format(
        consultant_name=consultant_name,
        data_json=json.dumps(all_rows, ensure_ascii=False, indent=2),
        snippets_text=join_snippets(snips_reco),
        datacard_text=datacard_text
    )

    summary_task = answer_llm.ainvoke(summary_prompt)
    reco_task    = answer_llm.ainvoke(reco_prompt)
    summary_text, reco_text = (await asyncio.gather(summary_task, reco_task))
    summary_text = summary_text.content.strip()
    reco_text    = reco_text.content.strip()

    # PASO 3 — Gráficos (mismo dataset)
    df_full = pd.DataFrame(all_rows)
    charts["Distribución por Estado"] = await build_aggregated_llm_chart(
        df=df_full, group_by_col='estado_de_defecto', agg_col='defecto',
        goal="gráfico de anillo con etiquetas 'estado_de_defecto' y valores 'cantidad_de_defecto'."
    )
    charts["Defectos por Módulo"] = await build_aggregated_llm_chart(
        df=df_full, group_by_col='modulo', agg_col='defecto',
        goal="gráfico de barras: X='modulo', Y='cantidad_de_defecto'."
    )
    charts["Antigüedad de Defectos"] = await build_llm_chart(all_rows,
        "gráfico de barras: X='defecto', Y='antiguedad_del_defecto_promedio_en_dias', orden descendente."
    )
    charts["Matriz de Inactividad y Riesgo"] = build_inactivity_risk_chart(df_full)
    charts["Esfuerzo por Hallazgo (Iteraciones)"] = build_effort_iterations_chart(df_full)

    # NUEVO: Contexto multimodal (solo si está habilitado)
    multimodal_context = {}
    if ENABLE_MULTIMODAL:
        from app.etl.retrieval_orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        multimodal_context = orchestrator.retrieve_for_multimodal_report(
            f"reportes análisis consultor {consultant_name}"
        )

    return {
        "preview_for": consultant_name,
        "sections": {
            "summary": {
                "text": summary_text,
                "generated_sql_raw": sql_full_data,
                "sql_template": sql_template,
                "required_columns": SUMMARY_REQUIRED_COLS,
                "evidence_ids": [s["id"] for s in snips_summary]
            },
            "recommendations": {
                "text": reco_text,
                "generated_sql_raw": sql_full_data,
                "sql_template": sql_template,
                "required_columns": RECO_REQUIRED_COLS,
                "evidence_ids": [s["id"] for s in snips_reco]
            }
        },
        "charts": {k: v for k, v in charts.items() if v},
        "datacard": datacard_text,
        "multimodal_context": multimodal_context
    }


async def generate_report_from_template(responsable: str, sql_template: str) -> Dict[str, Any]:
    """Genera TODO el reporte reutilizando una SQL plantilla ya aprobada (sin LLM-SQL)."""
    log.info(f"Generando reporte desde plantilla para: '{responsable}'")
    datacard_text = build_datacard()

    # 1) Ejecutar la SQL plantilla para este responsable
    final_sql = _fill_template(sql_template, responsable)
    rows = _exec_sql(final_sql)
    rows = normalize_rows(rows)

    if not ensure_columns(rows, SUMMARY_REQUIRED_COLS) or not ensure_columns(rows, RECO_REQUIRED_COLS):
        raise RuntimeError("Dataset de plantilla no cumple contrato básico para resumen/reco.")

    df = pd.DataFrame(rows)

    # 2) RAG de negocio
    snips_summary = get_business_snippets("resumen ejecutivo defectos KPI reglas definiciones calidad")
    snips_reco    = get_business_snippets("priorización plan de acción defectos reglas SLA")

    # 3) Textos (usando prompts dinámicos)
    summary_tpl = get_prompt("report_summary_prompt")
    reco_tpl    = get_prompt("report_recommendations_prompt")

    summary_prompt = summary_tpl.format(
        consultant_name=responsable,
        data_json=json.dumps(rows, ensure_ascii=False, indent=2),
        snippets_text=join_snippets(snips_summary),
        datacard_text=datacard_text
    )
    reco_prompt = reco_tpl.format(
        consultant_name=responsable,
        data_json=json.dumps(rows, ensure_ascii=False, indent=2),
        snippets_text=join_snippets(snips_reco),
        datacard_text=datacard_text
    )

    summary_task = answer_llm.ainvoke(summary_prompt)
    reco_task    = answer_llm.ainvoke(reco_prompt)
    summary_result, reco_result = await asyncio.gather(summary_task, reco_task)
    summary_text = summary_result.content.strip()
    reco_text    = reco_result.content.strip()

    # 4) Gráficos (reusamos builders)
    charts: Dict[str, Any] = {}
    charts["Distribución por Estado"] = await build_aggregated_llm_chart(
        df=df, group_by_col='estado_de_defecto', agg_col='defecto',
        goal="gráfico de anillo con etiquetas 'estado_de_defecto' y valores 'cantidad_de_defecto'."
    )
    charts["Defectos por Módulo"] = await build_aggregated_llm_chart(
        df=df, group_by_col='modulo', agg_col='defecto',
        goal="gráfico de barras: X='modulo', Y='cantidad_de_defecto'."
    )
    charts["Matriz de Inactividad y Riesgo"] = build_inactivity_risk_chart(df)
    charts["Esfuerzo por Hallazgo (Iteraciones)"] = build_effort_iterations_chart(df)

    # --- INICIO DEL CÓDIGO AÑADIDO ---
    multimodal_context = {}
    if ENABLE_MULTIMODAL:
        from app.etl.retrieval_orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        multimodal_context = orchestrator.retrieve_for_multimodal_report(
            f"reportes análisis consultor {responsable}"
        )
    # --- FIN DEL CÓDIGO AÑADIDO ---

    return {
        "preview_for": responsable,
        "sections": {
            "summary": {
                "text": summary_text,
                "sql_template": sql_template,
                "required_columns": SUMMARY_REQUIRED_COLS,
                "evidence_ids": [s["id"] for s in snips_summary]
            },
            "recommendations": {
                "text": reco_text,
                "sql_template": sql_template,
                "required_columns": RECO_REQUIRED_COLS,
                "evidence_ids": [s["id"] for s in snips_reco]
            }
        },
        "charts": {k: v for k, v in charts.items() if v},
        "datacard": datacard_text,
        "multimodal_context": multimodal_context
    }
