from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.agent.shared import AgentState, router_llm, answer_llm, RouteDecision
from app.tools.tools import sql_context_retriever, execute_duckdb_query
from app.agent.persona import AGENT_PERSONA
from app.agent.prompts import get_prompt
import logging
import re
import json
import duckdb
import plotly.express as px

logger = logging.getLogger(__name__)


if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


logger.info("🔧 NODES.PY MODULE LOADED - LOGGER IS WORKING")

_MAX_TURNS_BEFORE_SUMMARY = 18 
_KEEP_RECENT_TURNS = 10         
_SUMMARY_MAX_CHARS = 2000        

def _format_messages_for_summary(msgs: List[Any]) -> str:
    parts = []
    for m in msgs:
        if isinstance(m, HumanMessage):
            parts.append(f"Usuario: {m.content}")
        elif isinstance(m, AIMessage):
            parts.append(f"Asistente: {m.content}")
    return "\n".join(parts)

def memory_guard_node(state: AgentState) -> Dict[str, Any]:
    """
    Si hay muchos turnos, consolidamos los mensajes antiguos en `summary`.
    No borramos mensajes (LangGraph agrega por 'add'), pero el prompt usará
    solo la ventana reciente + el resumen.
    """
    messages = state.get("messages", []) or []
    if len(messages) <= _MAX_TURNS_BEFORE_SUMMARY:
        return {}

    # Consolidamos TODO menos la ventana reciente
    older = messages[:-_KEEP_RECENT_TURNS]
    if not older:
        return {}

    new_messages_text = _format_messages_for_summary(older)
    prev_summary = state.get("summary", "") or ""

    try:
        prompt_tmpl = get_prompt("memory_summarizer_system_prompt")
        chain = PromptTemplate.from_template(prompt_tmpl) | summarizer_llm | StrOutputParser()
        updated_summary = chain.invoke({"prev_summary": prev_summary, "new_messages": new_messages_text}).strip()
        if not updated_summary:
            updated_summary = prev_summary
        updated_summary = updated_summary[:_SUMMARY_MAX_CHARS]
        logger.info("✅ Memoria resumida/actualizada.")
        return {"summary": updated_summary}
    except Exception as e:
        logger.error(f"❌ Error en memory_guard_node: {e}")
        return {}

def get_conversation_context(state: AgentState, max_length: int = 3000, keep_recent: int = _KEEP_RECENT_TURNS) -> str:
    messages = state.get("messages", []) or []
    if not messages:
        summary = state.get("summary", "")
        return f"### RESUMEN ACUMULADO:\n{summary}" if summary else ""

    # Tomamos solo la ventana reciente
    recent = messages[-keep_recent:] if keep_recent > 0 else messages
    conversation_str = ""
    for msg in reversed(recent[:-1]):  # excluye el último (suele ser la pregunta actual)
        if isinstance(msg, HumanMessage):
            entry = f"Usuario: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            entry = f"Asistente: {msg.content}\n"
        else:
            continue
        if len(conversation_str) + len(entry) > max_length:
            break
        conversation_str = entry + conversation_str

    parts = []
    if state.get("summary"):
        parts.append("### RESUMEN ACUMULADO:\n" + state["summary"][:_SUMMARY_MAX_CHARS])
    if conversation_str:
        parts.append("### CONVERSACIÓN RECIENTE:\n" + conversation_str)
    return "\n\n".join(parts)

def router_node(state: AgentState) -> Dict[str, Any]:
    conversation_context = get_conversation_context(state)
    user_question = ""
    if messages := state.get("messages"):
        user_question = messages[-1].content

    prompt_template = get_prompt('router_system_prompt')
    system_prompt = prompt_template.format(
        conversation_context=conversation_context, 
        user_question=user_question
    )

    messages_for_llm = [SystemMessage(content=system_prompt)]
 
    try:
        result: RouteDecision = router_llm.invoke(messages_for_llm)
        logger.info(f"Router decision: {result.route}")
        
        if result.route == "end" and result.reply:
            return {"messages": [AIMessage(content=result.reply)], "route": result.route}
        
        return {"route": result.route}
    
    except Exception as e:
        logger.error(f"Error in router_node: {e}")
        return {"route": "answer"}

def sql_context_node(state: AgentState) -> Dict[str, Any]:
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")
    
    context = sql_context_retriever.invoke({"query": query})
    
    if "SQL_ERROR" in context:
        return {"sql_context": None, "sql_error": context}
    
    logger.info("SQL context retrieved successfully")
    return {"sql_context": context}

def sql_generation_node(state: AgentState) -> Dict[str, Any]:
    logger.info("ENTERING SQL_GENERATION_NODE")
    # Log detailed memory state at this point
    logger.info("=== MEMORY STATE AT SQL_GENERATION_NODE ===")
    logger.info("TEST LOG: This should appear in app.log")
    
    # Log messages
    if messages := state.get("messages"):
        logger.info(f"   MESSAGES ({len(messages)} total):")
        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                logger.info(f"     [{i}] Human: {msg.content[:100]!r}...")
            elif isinstance(msg, AIMessage):
                logger.info(f"     [{i}] AI: {msg.content[:100]!r}...")
    
    # Log SQL context
    if sql_context := state.get("sql_context"):
        logger.info(f"   SQL_CONTEXT ({len(sql_context)} chars): {sql_context[:200]!r}...")
    else:
        logger.info("   SQL_CONTEXT: None")
    
    # Log any existing SQL query
    if sql_query := state.get("sql_query"):
        logger.info(f"   SQL_QUERY ({len(sql_query)} chars): {sql_query!r}")
    else:
        logger.info("   SQL_QUERY: None")
    
    # Log any SQL result
    if sql_result := state.get("sql_result"):
        logger.info(f"   SQL_RESULT ({len(sql_result)} chars): {sql_result[:200]!r}...")
    else:
        logger.info("   SQL_RESULT: None")
    
    # Log any errors
    if sql_error := state.get("sql_error"):
        logger.info(f"   SQL_ERROR: {sql_error!r}")
    else:
        logger.info("   SQL_ERROR: None")
    
    if chart_error := state.get("chart_error"):
        logger.info(f"   CHART_ERROR: {chart_error!r}")
    else:
        logger.info("   CHART_ERROR: None")
    
    # Log retry count
    if retry_count := state.get("retry_count"):
        logger.info(f"   RETRY_COUNT: {retry_count}")
    else:
        logger.info("   RETRY_COUNT: 0")
    
    # Log route
    if route := state.get("route"):
        logger.info(f"   ROUTE: {route}")
    else:
        logger.info("   ROUTE: None")
    
    # Log chart spec
    if chart_spec := state.get("chart_spec"):
        logger.info(f"   CHART_SPEC: present (keys: {list(chart_spec.keys()) if isinstance(chart_spec, dict) else 'not dict'})")
    else:
        logger.info("   CHART_SPEC: None")
    
    logger.info("=== END MEMORY STATE ===")
    
    user_question = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )
    conversation_context = get_conversation_context(state, max_length=4000)
        
    context = state.get("sql_context", "")
    if not context:
        logger.info("❌ EXITING SQL_GENERATION_NODE - NO CONTEXT")
        return {"sql_error": "No database context available"}

    error_feedback = ""
    if state.get("sql_error"):
        error_feedback = f"""
        ATENCIÓN: La consulta anterior que generaste falló.
        Error: "{state['sql_error']}"
        Por favor, analiza el error y la pregunta original para generar una nueva consulta SQL corregida.
        """

    prompt_template = get_prompt('sql_generation_system_prompt')
    prompt = PromptTemplate.from_template(prompt_template)

    # Log the system prompt that will be used
    logger.info("=== SYSTEM PROMPT FOR SQL GENERATION ===")
    logger.info(f"   PROMPT_TEMPLATE ({len(prompt_template)} chars):")
    logger.info(f"   {prompt_template}")
    logger.info("=== END SYSTEM PROMPT ===")

    try:
        llm_chain = prompt | answer_llm | StrOutputParser()
        sql_query = llm_chain.invoke(
            {
                "error_feedback": error_feedback,
                "context": context,
                "question": user_question,
                "conversation_context": conversation_context,
            }
        )
        sql_query = sql_query.strip()
        sql_query = re.sub(r"```sql\n?", "", sql_query)
        sql_query = re.sub(r"```\n?", "", sql_query)
        sql_query = sql_query.strip()
        logger.info(f"Generated SQL query: {sql_query}")
        logger.info("EXITING SQL_GENERATION_NODE SUCCESSFULLY")
        
        return {"sql_query": sql_query, "sql_error": None}
    except Exception as e:
        logger.error(f"Error generating SQL: {e}")
        logger.info("EXITING SQL_GENERATION_NODE WITH ERROR")
        return {"sql_error": f"Error generating SQL query: {str(e)}"}
    
def sql_execution_node(state: AgentState) -> Dict[str, Any]:
    sql_query = state.get("sql_query", "")
    
    if not sql_query:
        return {"sql_error": "No SQL query to execute"}
    
    result_json_str = execute_duckdb_query.invoke({"sql_query": sql_query})
    
    try:
        result_data = json.loads(result_json_str)
        table_str = result_data.get("table_str", "")
        json_data = result_data.get("json_data")

        if table_str.startswith("SQL_ERROR"):
            retry_count = state.get("retry_count", 0) + 1
            logger.error(f"SQL Execution Error. Query: [{sql_query}]. Error: [{table_str}]")
            return {"sql_error": table_str, "retry_count": retry_count}

        logger.info("SQL query executed successfully")
        return {
            "sql_result": table_str, 
            "sql_result_json": json.dumps(json_data, ensure_ascii=False),
            "sql_error": None, 
            "retry_count": 0,
            "chart_spec": None,
            "chart_error": None
        }
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(f"Failed to parse tool output: {e}. Output: {result_json_str}")
        if isinstance(result_json_str, str) and result_json_str.startswith("SQL_ERROR"):
             logger.error(f"SQL Execution Error. Query: [{sql_query}]. Error: [{result_json_str}]")
             return {"sql_error": result_json_str, "retry_count": state.get("retry_count", 0) + 1}
        return {"sql_error": "Invalid data format from SQL tool.", "retry_count": state.get("retry_count", 0) + 1}

def chart_generation_node(state: AgentState) -> Dict[str, Any]:
    logger.info("Iniciando la generación del gráfico.")
    user_question = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )
    sql_result_json = state.get("sql_result_json")

    if not sql_result_json:
        logger.warning("No hay resultados SQL en formato JSON para generar el gráfico.")
        return {"chart_error": "No se encontraron datos (JSON) para graficar."}

    try:
        data_list = json.loads(sql_result_json)
        if not data_list:
            return {"chart_error": "Los datos para el gráfico están vacíos."}
    except json.JSONDecodeError as e:
        logger.error(f"Error al parsear el sql_result_json: {e}")
        return {"chart_error": f"Error interno al procesar los datos JSON: {e}"}

    prompt_template = get_prompt('chart_generation_system_prompt')
    
    try:
        chain = PromptTemplate.from_template(prompt_template) | answer_llm | StrOutputParser()
        chart_spec_str = chain.invoke({
            "user_question": user_question,
            "sql_result_json": sql_result_json
        })
        
        chart_spec_str = chart_spec_str.strip().replace("```json", "").replace("```", "")
        chart_spec = json.loads(chart_spec_str)
        
        if data_list:
            headers = data_list[0].keys()
            csv_header = ",".join(headers)
            csv_rows = [csv_header]
            for row in data_list:
                csv_rows.append(",".join(str(row.get(h, "")) for h in headers))
            chart_spec["data_csv"] = "\n".join(csv_rows)
        else:
            chart_spec["data_csv"] = ""

        logger.info("Especificación de gráfico generada exitosamente.")
        return {"chart_spec": chart_spec, "chart_error": None, "sql_result": None}
    
    except Exception as e:
        logger.error(f"Error generando la especificación del gráfico con el LLM: {e}")
        return {"chart_error": f"No se pudo generar la especificación del gráfico: {e}"}

def answer_node(state: AgentState) -> Dict[str, Any]:
    user_question = next((m.content for m in reversed(state["messages"])
                          if isinstance(m, HumanMessage)), "")
    
    conversation_context = get_conversation_context(state)
    
    context_for_prompt = ""

    task_guidance = ""
    question_lower = user_question.lower()
    if "resumen ejecutivo" in question_lower:
        task_guidance = "TAREA: RESUMEN EJECUTIVO"
    elif "prioridades" in question_lower or "plan de acción" in question_lower:
        task_guidance = "TAREA: PLAN DE ACCIÓN"
    
    if state.get("chart_spec"):
        context_for_prompt = "Se ha generado un gráfico exitosamente. Menciona esto en tu respuesta."
    elif state.get("sql_result"):
        sql_result = state.get("sql_result", "").replace("QUERY_RESULT::", "").strip()
        context_for_prompt = f"### RESULTADOS DE LA CONSULTA ACTUAL:\n{sql_result}"
    elif state.get("chart_error"):
        context_for_prompt = f"### ERROR EN GRÁFICO:\nHubo un problema al generar el gráfico: {state['chart_error']}"
    elif state.get("sql_error"):
        context_for_prompt = f"### ERROR EN LA CONSULTA ACTUAL:\n{state.get('sql_error')}"
    else:
        context_for_prompt = "No se encontró información relevante."

    prompt_template = get_prompt('answer_system_prompt')
    system_prompt = prompt_template.format(
        user_question=user_question,
        conversation_context=conversation_context,
        context_for_prompt=context_for_prompt,
        task_guidance=task_guidance
    )

    messages_for_llm = [SystemMessage(content=system_prompt)]

    ans = answer_llm.invoke(messages_for_llm).content

    return {"messages": [AIMessage(content=ans)]}