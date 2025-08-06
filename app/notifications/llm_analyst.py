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
    chart_spec = None

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
        logger.info(f"  Paso 3/3: Generando datos del gráfico para {consultant_name}...")
        chart_prompt = (
            f"Finalmente, genera un gráfico de barras que muestre la cantidad de defectos por módulo asignados a {consultant_name}."
        )
        chart_state = await agent_executor.ainvoke(
            {"messages": [HumanMessage(content=chart_prompt)]}, config
        )
        chart_spec = chart_state.get("chart_spec")
        if chart_spec:
            logger.info(f"  ...Datos del gráfico generados exitosamente.")
        else:
            logger.warning(f"  ...No se pudieron generar los datos para el gráfico.")

    except Exception as e:
        logger.error(
            f"Error crítico durante la generación del reporte para {consultant_name}: {e}",
            exc_info=True,
        )

    return {
        "summary": summary,
        "recommendations": recommendations,
        "chart_spec": chart_spec,
    }