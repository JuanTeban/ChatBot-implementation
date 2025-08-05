from typing import Dict, Any, TypedDict, Literal, Annotated, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
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

def router_node(state: AgentState) -> Dict[str, Any]:
    recent_messages = state.get("messages", [])[-6:] if state.get("messages") else []
    conversation_context = ""
    if len(recent_messages) > 1:
        conversation_context = "### CONVERSACIÓN RECIENTE:\n"
        for msg in recent_messages:
            if isinstance(msg, HumanMessage):
                conversation_context += f"Usuario: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                conversation_context += f"Asistente: {msg.content}\n"

    user_question = recent_messages[-1].content if recent_messages else ''

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
    user_question = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )
    recent_messages = state.get("messages", [])[-6:] if state.get("messages") else []
    conversation_context = ""
    if len(recent_messages) > 1:
        conversation_context = "\n**CONTEXTO CONVERSACIONAL RECIENTE:**\n"
        for msg in recent_messages[:-1]:
            if isinstance(msg, HumanMessage):
                conversation_context += f"Usuario preguntó: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                conversation_context += f"Sistema respondió: {msg.content}\n"
        conversation_context += "\n"
        
    context = state.get("sql_context", "")
    if not context:
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
        
        return {"sql_query": sql_query, "sql_error": None}
    except Exception as e:
        logger.error(f"Error generating SQL: {e}")
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
    logger.debug(f"DEBUGGING [1/4]: Estado de entrada del `answer_node`: {state}")

    user_question = next((m.content for m in reversed(state["messages"])
                          if isinstance(m, HumanMessage)), "")
    
    recent_messages = state.get("messages", [])[-6:] if state.get("messages") else []
    conversation_context = ""
    
    if len(recent_messages) > 1:
        conversation_context = "\n### CONTEXTO DE CONVERSACIÓN RECIENTE:\n"
        for msg in recent_messages[:-1]:
            if isinstance(msg, HumanMessage):
                conversation_context += f"👤 Usuario: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                conversation_context += f"🤖 Asistente: {msg.content}\n"
        conversation_context += "\n"
    
    context_for_prompt = ""
    
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
        agent_persona=AGENT_PERSONA,
        conversation_context=conversation_context,
        context_for_prompt=context_for_prompt
    )

    user_message = HumanMessage(content=f"Basándote en los datos y el contexto, responde: {user_question}")
    messages_for_llm = [SystemMessage(content=system_prompt), user_message]

    logger.debug(f"DEBUGGING [2/4]: Contexto EXACTO enviado al LLM final: {messages_for_llm}")

    ans = answer_llm.invoke(messages_for_llm).content
    logger.debug(f"DEBUGGING [3/4]: Respuesta CRUDA recibida del LLM: {ans}")

    return {"messages": [AIMessage(content=ans)]}
