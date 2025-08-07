import logging
import uuid
from typing import Any, Dict

from app.agent.langgraph_agent import get_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


async def generate_report_content(
    consultant_name: str, consultant_email: str
) -> Dict[str, Any]:
    """
    Invoca al agente con tareas específicas y secuenciales, permitiéndole
    usar su 'entrenamiento' (prompts.json) para cada paso.
    """
    agent_executor = get_agent()
    config = RunnableConfig(configurable={"thread_id": f"report-job-{uuid.uuid4()}"})

    summary = "No se pudo generar el resumen ejecutivo."
    recommendations = "No se pudieron generar las recomendaciones."
    charts = {}

    try:
        # --- TAREA 1: Generar el Resumen Ejecutivo ---
        logger.info(f"  Paso 1/3: Obteniendo resumen para {consultant_name}...")
        summary_prompt = (
            f"Genera un resumen ejecutivo de los defectos para el responsable {consultant_name}. Incluye el total de hallazgos, un desglose por estado, la cantidad de defectos bloqueantes y la antigüedad máxima encontrada."
        )
        summary_state = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=summary_prompt)]}, config
        )
        last_message = summary_state.get("messages", [])[-1]
        if isinstance(last_message, AIMessage):
            summary = last_message.content
            logger.info(f"  ...Resumen obtenido exitosamente.")

        # --- TAREA 2: Generar las Recomendaciones ---
        logger.info(f"  Paso 2/3: Obteniendo recomendaciones para {consultant_name}...")
        reco_prompt = (
            f"Ahora, para {consultant_name}, determina las 3 principales prioridades de trabajo basadas en la criticidad y antigüedad de los defectos. Lístalas para crear un plan de acción."
        )
        reco_state = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=reco_prompt)]}, config
        )
        last_message = reco_state.get("messages", [])[-1]
        if isinstance(last_message, AIMessage):
            recommendations = last_message.content
            logger.info(f"  ...Recomendaciones obtenidas exitosamente.")

        # --- TAREA 3: Generar el Gráfico ---
        logger.info(f"  Paso 3/6: Generando Gráfico Básico para {consultant_name}...")
        chart_prompt_basic = (
            f"Genera un gráfico de barras que muestre la cantidad de defectos por módulo asignados a {consultant_name}."
        )
        chart_state_basic = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt_basic)]}, config
        )
        if chart_spec := chart_state_basic.get("chart_spec"):
            charts["Cantidad de Defectos por Módulo"] = chart_spec
            logger.info(f"  ...Gráfico Básico generado.")

        # --- TAREA 4: Generar el Gráfico de Prioridades ---
        logger.info(f"  Paso 4/6: Generando Gráfico de Priorización para {consultant_name}...")
        chart_prompt_prio = (
            f"Para {consultant_name}, genera un gráfico de anillo que muestre la distribución de hallazgos Bloqueantes vs. No Bloqueantes. Considera los valores nulos o vacíos en la columna 'bloqueante_escenarios' como 'No Bloqueante'."
        )
        chart_state_prio = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt_prio)]}, config
        )
        if chart_spec := chart_state_prio.get("chart_spec"):
            charts["Priorización de Hallazgos"] = chart_spec
            logger.info(f"  ...Gráfico de Priorización generado.")

        # --- TAREA 5: Generar el Gráfico de tiemp ---
        logger.info(f"  Paso 5/6: Generando Gráfico de Responsabilidad Actual para {consultant_name}...")
        chart_prompt_resp = (
            f"Para {consultant_name}, crea un gráfico de barras. El eje Y debe mostrar la antigüedad de cada defecto. El eje X deben ser los defectos. El color de cada barra debe indicar la responsabilidad actual: 'IBM' si el estado es 'Nuevo' o 'En tratamiento', y 'EPM' para los demás estados."
        )
        chart_state_resp = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt_resp)]}, config
        )
        if chart_spec := chart_state_resp.get("chart_spec"):
            charts["Responsabilidad Actual por Antigüedad"] = chart_spec
            logger.info(f"  ...Gráfico de Responsabilidad generado.")

        # --- TAREA 6: Generar el Gráfico de Inactividad ---
        logger.info(f"  Paso 6/6: Generando Gráfico de Inactividad para {consultant_name}...")
        chart_prompt_inactivity = (
            f"Para {consultant_name}, genera un gráfico de dispersión (scatter plot) que relacione la 'Antigüedad Total' (eje x) con los 'Días desde Última Actividad' (eje y). Los días desde última actividad deben calcularse a partir de la fecha más reciente encontrada en la columna 'comentarios'."
        )
        chart_state_inactivity = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt_inactivity)]}, config
        )
        if chart_spec := chart_state_inactivity.get("chart_spec"):
            charts["Matriz de Inactividad y Riesgo"] = chart_spec
            logger.info(f"  ...Gráfico de Inactividad generado.")

        # --- TAREA 6: Generar el Gráfico de Esfuerzo ---
        logger.info(f"  Paso 6/6: Generando Gráfico de Esfuerzo para {consultant_name}...")
        chart_prompt_effort = (
            f"Para el responsable '{consultant_name}', genera un gráfico de barras que muestre el número de 'iteraciones' por cada defecto. Debes buscar el nombre del consultor en la columna 'responsable_del_defecto'. Las iteraciones se calculan contando el número de fechas en la columna 'comentarios'."
        )
        chart_state_effort = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt_effort)]}, config
        )
        if chart_spec := chart_state_effort.get("chart_spec"):
            charts["Esfuerzo por Hallazgo (Iteraciones)"] = chart_spec
            logger.info(f"  ...Gráfico de Esfuerzo generado.")


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