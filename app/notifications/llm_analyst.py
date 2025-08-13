import logging
import uuid
from typing import Any, Dict

from app.agent.langgraph_agent import get_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

import duckdb, re, json
import pandas as pd
from datetime import datetime, timezone
import plotly.express as px
import plotly.io as pio

logger = logging.getLogger(__name__)

# === Constantes de datos (ajusta si en tu ETL usaste otros alias) ===
TABLE = "seguimiento_hallazgos_solman_seguimiento_detalles_defecto"
COL_RESP = "responsable_del_defecto"
COL_DEFECTO = "defecto"
COL_COMENT = "comentarios"
COL_AGE = "antiguedad_del_defecto_promedio_en_dias"

# Fechas en comentarios: dd/mm/yyyy o dd/mm/yy (también acepta separador "-")
_DATE_RE = re.compile(r"(?:^|[^0-9])(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?:[^0-9]|$)")

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _to_float_locale(x):
    """Convierte strings con coma decimal y separador de miles a float.
       '19,70' -> 19.70 ; '1.234,56' -> 1234.56 ; maneja None/NaN."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace('\xa0', '').replace(' ', '')
    if s == '' or s.lower() == 'nan':
        return None
    if ',' in s:
        if '.' in s:  # quita separador de miles estilo europeo
            s = s.replace('.', '')
        s = s.replace(',', '.')
    return float(s)

def _load_df_for_responsible(name: str) -> pd.DataFrame:
    """Carga todas las filas para el responsable (LIKE case-insensitive)."""
    from app.config.settings import DUCKDB_PATH
    con = duckdb.connect(database=str(DUCKDB_PATH), read_only=True)
    q = f"""
        SELECT *
        FROM {TABLE}
        WHERE UPPER({COL_RESP}) LIKE UPPER('%{name}%')
    """
    df = con.execute(q).fetchdf()
    con.close()
    return df

def _parse_dates_from_text(s: str):
    """Extrae todas las fechas dd/mm/yyyy o dd/mm/yy que aparezcan en texto."""
    if not isinstance(s, str) or not s.strip():
        return []
    out = []
    for m in _DATE_RE.findall(s.replace("\n", " ")):
        d = m.replace("-", "/")
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                out.append(datetime.strptime(d, fmt).replace(tzinfo=timezone.utc))
                break
            except ValueError:
                continue
    return out

def _fig_to_jsonsafe_spec(fig):
    """Convierte una figura Plotly a un dict 100% JSON-safe (sin ndarray)."""
    return json.loads(pio.to_json(fig, validate=False))

# -------------------------------------------------------------------
# Gráficos deterministas (sin LLM)
# -------------------------------------------------------------------

def build_inactivity_risk_chart_spec(consultant_name: str):
    """
    Scatter: X = Antigüedad Total (días), Y = Días desde Última Actividad
    Última actividad se toma como la fecha más reciente detectada en 'comentarios'.
    """
    df = _load_df_for_responsible(consultant_name)
    if df.empty or COL_COMENT not in df or COL_AGE not in df:
        return None

    today = datetime.now(timezone.utc)
    ages, last_days, labels = [], [], []

    for _, r in df.iterrows():
        ages.append(_to_float_locale(r.get(COL_AGE)))
        dates = _parse_dates_from_text(str(r.get(COL_COMENT, "")))
        last = max(dates) if dates else None
        last_days.append((today - last).days if last else None)
        labels.append(str(r.get(COL_DEFECTO, "")))

    plot_df = pd.DataFrame({
        "Antigüedad Total": ages,
        "Días desde Última Actividad": last_days,
        "Defecto": labels
    }).dropna(subset=["Antigüedad Total", "Días desde Última Actividad"])

    if plot_df.empty:
        return None

    fig = px.scatter(
        plot_df,
        x="Antigüedad Total",
        y="Días desde Última Actividad",
        hover_name="Defecto",
        title="Relación entre Antigüedad Total y Días desde Última Actividad"
    )
    return _fig_to_jsonsafe_spec(fig)

def build_effort_iterations_chart_spec(consultant_name: str):
    """
    Barras: Iteraciones por Defecto (conteo de fechas encontradas en 'comentarios').
    """
    df = _load_df_for_responsible(consultant_name)
    if df.empty or COL_COMENT not in df:
        return None

    rows = []
    for _, r in df.iterrows():
        defect = str(r.get(COL_DEFECTO, ""))
        n_dates = len(_parse_dates_from_text(str(r.get(COL_COMENT, ""))))
        rows.append((defect, n_dates))

    plot_df = (
        pd.DataFrame(rows, columns=["Defecto", "Iteraciones"])
        .groupby("Defecto", as_index=False)["Iteraciones"].sum()
        .sort_values("Iteraciones", ascending=False)
    )

    if plot_df.empty:
        return None

    fig = px.bar(
        plot_df,
        x="Defecto",
        y="Iteraciones",
        title=f"Número de Iteraciones por Defecto para {consultant_name}"
    )
    fig.update_xaxes(tickangle=-45)
    return _fig_to_jsonsafe_spec(fig)

# -------------------------------------------------------------------
# Orquestador (usa tu agente + añade los dos gráficos deterministas)
# -------------------------------------------------------------------

async def generate_report_content(
    consultant_name: str, consultant_email: str
) -> Dict[str, Any]:
    """
    Invoca al agente con tareas específicas y secuenciales, y añade
    los 2 gráficos deterministas para evitar errores de parseo.
    """
    agent_executor = get_agent()
    config = RunnableConfig(configurable={"thread_id": f"report-job-{uuid.uuid4()}"})

    summary = "No se pudo generar el resumen ejecutivo."
    recommendations = "No se pudieron generar las recomendaciones."
    charts: Dict[str, Any] = {}

    try:
        # --- TAREA 1: Resumen ---
        logger.info(f"  Paso 1/7: Obteniendo resumen para {consultant_name}...")
        summary_prompt = (
            f"Genera un resumen ejecutivo de los defectos para el responsable {consultant_name}. "
            f"Incluye el total de hallazgos, un desglose por estado, la cantidad de defectos bloqueantes "
            f"y la antigüedad máxima encontrada."
        )
        summary_state = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=summary_prompt)]}, config
        )
        last_message = summary_state.get("messages", [])[-1]
        if isinstance(last_message, AIMessage):
            summary = last_message.content
            logger.info("  ...Resumen obtenido exitosamente.")

        # --- TAREA 2: Recomendaciones ---
        logger.info(f"  Paso 2/7: Obteniendo recomendaciones para {consultant_name}...")
        reco_prompt = (
            f"Para {consultant_name}, determina las 3 principales prioridades de trabajo basadas "
            f"en la criticidad y la antigüedad de los defectos. Lístalas para un plan de acción."
        )
        reco_state = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=reco_prompt)]}, config
        )
        last_message = reco_state.get("messages", [])[-1]
        if isinstance(last_message, AIMessage):
            recommendations = last_message.content
            logger.info("  ...Recomendaciones obtenidas exitosamente.")

        # --- TAREA 3: Gráfico básico (LLM) ---
        logger.info(f"  Paso 3/7: Generando Gráfico Básico para {consultant_name}...")
        chart_prompt_basic = (
            f"Genera un gráfico de barras que muestre la cantidad de defectos por módulo "
            f"asignados a {consultant_name}."
        )
        chart_state_basic = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt_basic)]}, config
        )
        if chart_spec := chart_state_basic.get("chart_spec"):
            charts["Cantidad de Defectos por Módulo"] = chart_spec
            logger.info("  ...Gráfico Básico generado.")

        # --- TAREA 4: Priorización (LLM) ---
        logger.info(f"  Paso 4/7: Generando Gráfico de Priorización para {consultant_name}...")
        chart_prompt_prio = (
            f"Para {consultant_name}, genera un gráfico de anillo que muestre la distribución "
            f"de hallazgos Bloqueantes vs. No Bloqueantes. Considera nulos/vacíos en "
            f"'bloqueante_escenarios' como 'No Bloqueante'."
        )
        chart_state_prio = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt_prio)]}, config
        )
        if chart_spec := chart_state_prio.get("chart_spec"):
            charts["Priorización de Hallazgos"] = chart_spec
            logger.info("  ...Gráfico de Priorización generado.")

        # --- TAREA 5: Responsabilidad actual (LLM) ---
        logger.info(f"  Paso 5/7: Generando Gráfico de Responsabilidad Actual para {consultant_name}...")
        chart_prompt_resp = (
            f"Para {consultant_name}, crea un gráfico de barras. El eje Y debe mostrar la antigüedad "
            f"de cada defecto. El eje X deben ser los defectos. El color de cada barra debe indicar "
            f"la responsabilidad actual: 'IBM' si el estado es 'Nuevo' o 'En tratamiento', y 'EPM' "
            f"para los demás estados."
        )
        chart_state_resp = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt_resp)]}, config
        )
        if chart_spec := chart_state_resp.get("chart_spec"):
            charts["Responsabilidad Actual por Antigüedad"] = chart_spec
            logger.info("  ...Gráfico de Responsabilidad generado.")

        # --- TAREA 6: Inactividad y riesgo (DET) ---
        logger.info(f"  Paso 6/7: Generando Gráfico de Inactividad (determinista) para {consultant_name}...")
        spec_inact = build_inactivity_risk_chart_spec(consultant_name)
        if spec_inact:
            charts["Matriz de Inactividad y Riesgo"] = spec_inact
        else:
            # Fallback (solo si faltan columnas): prompt equivalente
            chart_prompt_inactivity = (
                f"Genera un gráfico de dispersión (scatter) con X=antigüedad del defecto en días "
                f"y Y=días desde la última actividad (estimada leyendo las fechas en 'comentarios'). "
                f"Etiquetas por defecto."
            )
            chart_state_inactivity = await agent_executor.ainvoke(
                {"messages": [HumanMessage(content=chart_prompt_inactivity)]}, config
            )
            if chart_spec := chart_state_inactivity.get("chart_spec"):
                charts["Matriz de Inactividad y Riesgo"] = chart_spec

        # --- TAREA 7: Esfuerzo/Iteraciones (DET) ---
        logger.info(f"  Paso 7/7: Generando Gráfico de Esfuerzo (determinista) para {consultant_name}...")
        spec_eff = build_effort_iterations_chart_spec(consultant_name)
        if spec_eff:
            charts["Esfuerzo por Hallazgo (Iteraciones)"] = spec_eff
        else:
            chart_prompt_effort = (
                f"Genera un gráfico de barras con el número de iteraciones por defecto, "
                f"contando cuántas fechas aparecen en 'comentarios' para cada defecto."
            )
            chart_state_effort = await agent_executor.ainvoke(
                {"messages": [HumanMessage(content=chart_prompt_effort)]}, config
            )
            if chart_spec := chart_state_effort.get("chart_spec"):
                charts["Esfuerzo por Hallazgo (Iteraciones)"] = chart_spec

    except Exception as e:
        logger.error(
            f"Error crítico durante la generación del reporte para {consultant_name}: {e}",
            exc_info=True,
        )

    return {
        "summary": summary,
        "recommendations": recommendations,
        "charts": charts,
    }
