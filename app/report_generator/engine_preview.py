import json
import logging
import re
import time
from typing import Dict, Any, List, Tuple
import pandas as pd
import asyncio

from app.agent.shared import answer_llm
from app.tools.tools import execute_duckdb_query
from app.utils.report_logger import report_flow_logger
from .prompts import build_sql_prompt, get_prompt
from .rag import get_schema_context, get_business_snippets, join_snippets, get_multimodal_evidence, join_multimodal_evidence, extract_defect_from_data, get_summary_table_evidence, join_table_evidence
from .contracts import (
    ensure_columns, normalize_rows, build_datacard,
    SUMMARY_REQUIRED_COLS, RECO_REQUIRED_COLS
)
# from app.config.settings import ENABLE_MULTIMODAL  # REMOVIDO: no se usa
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
    raw = execute_duc0kdb_query.invoke({"sql_query": sql})
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
    
    # 🔍 LOG: Registrar generación de SQL
    report_flow_logger.log_rag_context_detailed(
        query=question,
        context_type="esquemas",
        retrieved_context=schema_ctx,
        source_count=1 if schema_ctx and schema_ctx.strip() else 0,
        collection_name="schema_knowledge",
        embedding_model="Gemini Embedding"
    )
    
    resp = answer_llm.invoke(prompt).content.strip()
    resp = re.sub(r"```sql|```", "", resp).strip()
    if not re.match(r"(?is)^\s*select\s", resp):
        raise RuntimeError("La SQL generada no inicia con SELECT.")
    resp = resp.rstrip(';').strip()
    final_sql = resp + ";"
    
    # 🔍 LOG: Registrar SQL generada
    report_flow_logger.log_sql_generation(
        question=question,
        schema_context=schema_ctx,
        generated_sql=final_sql
    )
    
    return final_sql

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
    try:
        rows = _extract_rows(raw)
        # 🔍 LOG: Registrar ejecución exitosa
        report_flow_logger.log_sql_execution(
            sql=sql,
            result_count=len(rows),
            execution_success=True
        )
        return rows
    except Exception as e:
        # 🔍 LOG: Registrar ejecución fallida
        report_flow_logger.log_sql_execution(
            sql=sql,
            result_count=0,
            execution_success=False,
            error=str(e)
        )
        raise

async def generate_report_preview(consultant_name: str) -> Dict[str, Any]:
    # 🔍 LOG: Iniciar generación de reporte
    start_time = time.time()
    report_flow_logger.start_report_generation(consultant_name, "preview")
    
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
    # Obtener contexto de esquemas para el resumen
    schema_ctx = get_schema_context(q_full_data)
    snips_summary = get_business_snippets("resumen ejecutivo defectos KPI reglas definiciones calidad")
    snips_reco = get_business_snippets("priorización plan de acción defectos reglas SLA")
    
    # 🔍 NUEVO: Recuperar evidencia de TABLAS para el RESUMEN
    defecto_especifico = extract_defect_from_data(all_rows)
    summary_table_evidence = get_summary_table_evidence(defecto=defecto_especifico)
    
    # 🔍 NUEVO: Recuperar evidencia multimodal para recomendaciones
    multimodal_evidence = get_multimodal_evidence(
        query="plan de acción priorización defectos evidencia hallazgos",
        responsable=consultant_name,
        defecto=defecto_especifico  # Usar defecto específico si está disponible
        # Sin k para recuperar TODOS los elementos disponibles
    )
    
    # 🔍 LOG: Registrar snippets obtenidos
    report_flow_logger.log_business_snippets(
        query="resumen ejecutivo defectos KPI reglas definiciones calidad",
        snippets=snips_summary,
        snippet_type="resumen"
    )
    report_flow_logger.log_business_snippets(
        query="priorización plan de acción defectos reglas SLA",
        snippets=snips_reco,
        snippet_type="recomendaciones"
    )

    summary_tpl = get_prompt("report_summary_prompt")
    reco_tpl    = get_prompt("report_recommendations_prompt")

    summary_prompt = summary_tpl.format(
        consultant_name=consultant_name,
        data_json=json.dumps(all_rows, ensure_ascii=False, indent=2),
        snippets_text=join_snippets(snips_summary),
        table_evidence_text=join_table_evidence(summary_table_evidence),  # 🔍 NUEVO: Evidencia de tablas
        datacard_text=datacard_text
    )
    
    # 🔍 NUEVO: Incluir evidencia multimodal en el prompt de recomendaciones
    multimodal_context = join_multimodal_evidence(multimodal_evidence)
    reco_prompt = reco_tpl.format(
        consultant_name=consultant_name,
        data_json=json.dumps(all_rows, ensure_ascii=False, indent=2),
        snippets_text=join_snippets(snips_reco),
        datacard_text=datacard_text,
        multimodal_evidence=multimodal_context  # Nuevo parámetro
    )

    summary_task = answer_llm.ainvoke(summary_prompt)
    reco_task    = answer_llm.ainvoke(reco_prompt)
    summary_result, reco_result = (await asyncio.gather(summary_task, reco_task))
    summary_text = summary_result.content.strip()
    reco_text    = reco_result.content.strip()
    
    # 🔍 LOG: Registrar prompts y respuestas del LLM
    report_flow_logger.log_llm_prompt_and_response(
        prompt_type="resumen_ejecutivo",
        prompt=summary_prompt,
        response=summary_text,
        consultant_name=consultant_name
    )
    report_flow_logger.log_llm_prompt_and_response(
        prompt_type="recomendaciones",
        prompt=reco_prompt,
        response=reco_text,
        consultant_name=consultant_name
    )

    # PASO 3 — Gráficos (mismo dataset)
    df_full = pd.DataFrame(all_rows)
    
    # 🔍 LOG: Registrar procesamiento de datos para gráficos
    report_flow_logger.log_data_processing(
        step="preparación_gráficos",
        input_count=len(all_rows),
        output_count=len(df_full),
        details=f"DataFrame creado con {len(df_full.columns)} columnas"
    )
    
    try:
        charts["Distribución por Estado"] = await build_aggregated_llm_chart(
            df=df_full, group_by_col='estado_de_defecto', agg_col='defecto',
            goal="gráfico de anillo con etiquetas 'estado_de_defecto' y valores 'cantidad_de_defecto'."
        )
        report_flow_logger.log_chart_generation(
            chart_title="Distribución por Estado",
            chart_type="gráfico_anillo_agregado",
            data_points=len(df_full['estado_de_defecto'].unique()) if 'estado_de_defecto' in df_full.columns else 0,
            success=bool(charts["Distribución por Estado"])
        )
    except Exception as e:
        report_flow_logger.log_chart_generation(
            chart_title="Distribución por Estado",
            chart_type="gráfico_anillo_agregado",
            data_points=0,
            success=False,
            error=str(e)
        )
        charts["Distribución por Estado"] = {}
    
    try:
        charts["Defectos por Módulo"] = await build_aggregated_llm_chart(
            df=df_full, group_by_col='modulo', agg_col='defecto',
            goal="gráfico de barras: X='modulo', Y='cantidad_de_defecto'."
        )
        report_flow_logger.log_chart_generation(
            chart_title="Defectos por Módulo",
            chart_type="gráfico_barras_agregado",
            data_points=len(df_full['modulo'].unique()) if 'modulo' in df_full.columns else 0,
            success=bool(charts["Defectos por Módulo"])
        )
    except Exception as e:
        report_flow_logger.log_chart_generation(
            chart_title="Defectos por Módulo",
            chart_type="gráfico_barras_agregado",
            data_points=0,
            success=False,
            error=str(e)
        )
        charts["Defectos por Módulo"] = {}
    
    try:
        charts["Antigüedad de Defectos"] = await build_llm_chart(all_rows,
            "gráfico de barras: X='defecto', Y='antiguedad_del_defecto_promedio_en_dias', orden descendente."
        )
        report_flow_logger.log_chart_generation(
            chart_title="Antigüedad de Defectos",
            chart_type="gráfico_barras_llm",
            data_points=len(all_rows),
            success=bool(charts["Antigüedad de Defectos"])
        )
    except Exception as e:
        report_flow_logger.log_chart_generation(
            chart_title="Antigüedad de Defectos",
            chart_type="gráfico_barras_llm",
            data_points=0,
            success=False,
            error=str(e)
        )
        charts["Antigüedad de Defectos"] = {}
    
    try:
        charts["Matriz de Inactividad y Riesgo"] = build_inactivity_risk_chart(df_full)
        report_flow_logger.log_chart_generation(
            chart_title="Matriz de Inactividad y Riesgo",
            chart_type="scatter_inactividad",
            data_points=len(df_full),
            success=bool(charts["Matriz de Inactividad y Riesgo"])
        )
    except Exception as e:
        report_flow_logger.log_chart_generation(
            chart_title="Matriz de Inactividad y Riesgo",
            chart_type="scatter_inactividad",
            data_points=0,
            success=False,
            error=str(e)
        )
        charts["Matriz de Inactividad y Riesgo"] = {}
    
    try:
        charts["Esfuerzo por Hallazgo (Iteraciones)"] = build_effort_iterations_chart(df_full)
        report_flow_logger.log_chart_generation(
            chart_title="Esfuerzo por Hallazgo (Iteraciones)",
            chart_type="barras_iteraciones",
            data_points=len(df_full),
            success=bool(charts["Esfuerzo por Hallazgo (Iteraciones)"])
        )
    except Exception as e:
        report_flow_logger.log_chart_generation(
            chart_title="Esfuerzo por Hallazgo (Iteraciones)",
            chart_type="barras_iteraciones",
            data_points=0,
            success=False,
            error=str(e)
        )
        charts["Esfuerzo por Hallazgo (Iteraciones)"] = {}

    try:
        result = {
            "preview_for": consultant_name,
            "sections": {
                "summary": {
                    "text": summary_text,
                    "generated_sql_raw": sql_full_data,
                    "sql_template": sql_template,
                    "required_columns": SUMMARY_REQUIRED_COLS,
                    "evidence_ids": [s.get("evidence_id", "unknown") for s in snips_summary]
                },
                "recommendations": {
                    "text": reco_text,
                    "generated_sql_raw": sql_full_data,
                    "sql_template": sql_template,
                    "required_columns": RECO_REQUIRED_COLS,
                    "evidence_ids": [s.get("evidence_id", "unknown") for s in snips_reco]
                }
            },
            "charts": {k: v for k, v in charts.items() if v},
            "datacard": datacard_text
        }
        
        # 🔍 LOG: Resumen completo de información RAG recuperada
        all_rag_data = {
            'schema_context': {
                'context': schema_ctx,
                'source_count': 1 if schema_ctx and schema_ctx.strip() else 0
            },
            'business_snippets': {
                'summary': snips_summary,
                'recommendations': snips_reco
            },
            'multimodal_evidence': multimodal_evidence
        }
        report_flow_logger.log_rag_summary(all_rag_data)
        
        # 🔍 LOG: Finalizar generación exitosa
        execution_time = time.time() - start_time
        successful_charts = len([v for v in charts.values() if v])
        report_flow_logger.finish_report_generation(
            consultant_name=consultant_name,
            success=True,
            total_charts=successful_charts,
            execution_time=execution_time
        )
        
        return result
        
    except Exception as e:
        # 🔍 LOG: Error en generación
        execution_time = time.time() - start_time
        report_flow_logger.log_error(
            error_type="generación_reporte",
            error_message=str(e),
            context=f"Consultor: {consultant_name}"
        )
        report_flow_logger.finish_report_generation(
            consultant_name=consultant_name,
            success=False,
            total_charts=0,
            execution_time=execution_time
        )
        raise


async def generate_report_from_template(responsable: str, sql_template: str) -> Dict[str, Any]:
    """Genera TODO el reporte reutilizando una SQL plantilla ya aprobada (sin LLM-SQL)."""
    # 🔍 LOG: Iniciar generación desde plantilla
    start_time = time.time()
    report_flow_logger.start_report_generation(responsable, "from_template")
    report_flow_logger.log_template_operation("usar_plantilla", sql_template, responsable)
    
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
    
    # 🔍 NUEVO: Recuperar evidencia de TABLAS para el RESUMEN
    defecto_especifico = extract_defect_from_data(rows)
    summary_table_evidence = get_summary_table_evidence(defecto=defecto_especifico)
    
    # 🔍 NUEVO: Recuperar evidencia multimodal para recomendaciones
    multimodal_evidence = get_multimodal_evidence(
        query="plan de acción priorización defectos evidencia hallazgos",
        responsable=responsable,
        defecto=defecto_especifico  # Usar defecto específico si está disponible
        # Sin k para recuperar TODOS los elementos disponibles
    )

    # 3) Textos (usando prompts dinámicos)
    summary_tpl = get_prompt("report_summary_prompt")
    reco_tpl    = get_prompt("report_recommendations_prompt")

    summary_prompt = summary_tpl.format(
        consultant_name=responsable,
        data_json=json.dumps(rows, ensure_ascii=False, indent=2),
        snippets_text=join_snippets(snips_summary),
        table_evidence_text=join_table_evidence(summary_table_evidence),  # 🔍 NUEVO: Evidencia de tablas
        datacard_text=datacard_text
    )
    
    # 🔍 NUEVO: Incluir evidencia multimodal en el prompt de recomendaciones
    multimodal_context = join_multimodal_evidence(multimodal_evidence)
    reco_prompt = reco_tpl.format(
        consultant_name=responsable,
        data_json=json.dumps(rows, ensure_ascii=False, indent=2),
        snippets_text=join_snippets(snips_reco),
        datacard_text=datacard_text,
        multimodal_evidence=multimodal_context  # Nuevo parámetro
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

    try:
        result = {
            "preview_for": responsable,
            "sections": {
                "summary": {
                    "text": summary_text,
                    "sql_template": sql_template,
                    "required_columns": SUMMARY_REQUIRED_COLS,
                    "evidence_ids": [s.get("evidence_id", "unknown") for s in snips_summary]
                },
                "recommendations": {
                    "text": reco_text,
                    "sql_template": sql_template,
                    "required_columns": RECO_REQUIRED_COLS,
                    "evidence_ids": [s.get("evidence_id", "unknown") for s in snips_reco]
                }
            },
            "charts": {k: v for k, v in charts.items() if v},
            "datacard": datacard_text
        }
        
        # 🔍 LOG: Resumen completo de información RAG recuperada
        all_rag_data = {
            'business_snippets': {
                'summary': snips_summary,
                'recommendations': snips_reco
            },
            'multimodal_evidence': multimodal_evidence
        }
        report_flow_logger.log_rag_summary(all_rag_data)
        
        # 🔍 LOG: Finalizar generación exitosa desde plantilla
        execution_time = time.time() - start_time
        successful_charts = len([v for v in charts.values() if v])
        report_flow_logger.finish_report_generation(
            consultant_name=responsable,
            success=True,
            total_charts=successful_charts,
            execution_time=execution_time
        )
        
        return result
        
    except Exception as e:
        # 🔍 LOG: Error en generación desde plantilla
        execution_time = time.time() - start_time
        report_flow_logger.log_error(
            error_type="generación_desde_plantilla",
            error_message=str(e),
            context=f"Responsable: {responsable}"
        )
        report_flow_logger.finish_report_generation(
            consultant_name=responsable,
            success=False,
            total_charts=0,
            execution_time=execution_time
        )
        raise
