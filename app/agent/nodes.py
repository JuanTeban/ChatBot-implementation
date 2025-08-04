from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.agent.shared import AgentState, router_llm, answer_llm, RouteDecision
from app.tools.tools import rag_search_tool, sql_context_retriever, execute_duckdb_query
from app.agent.persona import AGENT_PERSONA
from app.agent.prompts import get_prompt
import logging
import re

logger = logging.getLogger(__name__)





def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Decide la siguiente acción a tomar basándose en la pregunta del usuario y el contexto.
    """
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


def rag_node(state: AgentState) -> Dict[str, Any]:
    """
    (Actualmente no utilizado en el grafo) Realiza una búsqueda RAG.
    """
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")
    
    chunks = rag_search_tool.invoke({"query": query})
    
    if not chunks or "RAG_ERROR" in chunks:
        return {"rag": None, "route": "answer"}

    return {"rag": chunks, "route": "answer"}

def sql_context_node(state: AgentState) -> Dict[str, Any]:
    """
    Recupera el contexto de la base de datos relevante para la pregunta del usuario.
    """
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")
    
    context = sql_context_retriever.invoke({"query": query})
    
    if "SQL_ERROR" in context:
        return {"sql_context": None, "sql_error": context, "route": "answer"}
    
    logger.info("SQL context retrieved successfully")
    return {"sql_context": context, "route": "sql_generation"}

def sql_generation_node(state: AgentState) -> Dict[str, Any]:
    """
    Genera una consulta SQL basada en la pregunta del usuario y el contexto.
    """
    user_question = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
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
        return {"sql_error": "No database context available", "route": "answer"}

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
        
        # Limpiar el error anterior si se generó una nueva consulta
        return {"sql_query": sql_query, "sql_error": None, "route": "sql_execution"}
    except Exception as e:
        logger.error(f"Error generating SQL: {e}")
        return {"sql_error": f"Error generating SQL query: {str(e)}", "route": "answer"}
    

def sql_execution_node(state: AgentState) -> Dict[str, Any]:
    """
    Ejecuta la consulta SQL generada en la base de datos DuckDB.
    """
    sql_query = state.get("sql_query", "")
    
    if not sql_query:
        return {"sql_error": "No SQL query to execute", "route": "answer"}
    
    result = execute_duckdb_query.invoke({"sql_query": sql_query})
    
    if result.startswith("SQL_ERROR"):
        # Contamos el reintento
        retry_count = state.get("retry_count", 0) + 1
        return {"sql_error": result, "retry_count": retry_count}

    logger.info("SQL query executed successfully")
    return {"sql_result": result, "route": "answer", "sql_error": None, "retry_count": 0}

def answer_node(state: AgentState) -> Dict[str, Any]:
    """
    Genera la respuesta final en lenguaje natural para el usuario.
    """
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
    
    sql_query_context = ""
    if state.get("sql_query"):
        sql_query_context = f"### CONSULTA SQL EJECUTADA:\n```sql\n{state.get('sql_query')}\n```\n\n"
    
    context_for_prompt = "No se encontró información relevante."
    
    if state.get("sql_result"):
        sql_result = state.get("sql_result", "").replace("QUERY_RESULT::", "").strip()
        context_for_prompt = f"{sql_query_context}### RESULTADOS DE LA CONSULTA ACTUAL:\n{sql_result}"
    elif state.get("sql_error"):
        context_for_prompt = f"{sql_query_context}### ERROR EN LA CONSULTA ACTUAL:\n{state.get('sql_error')}"

    prompt_template = get_prompt('answer_system_prompt')
    system_prompt = prompt_template.format(
        user_question=user_question,
        agent_persona=AGENT_PERSONA,
        conversation_context=conversation_context,
        context_for_prompt=context_for_prompt
    )

    user_message = HumanMessage(content=f"Basándote en los datos actuales y el contexto conversacional, responde: {user_question}")
    messages_for_llm = [SystemMessage(content=system_prompt), user_message]

    logger.debug(f"DEBUGGING [2/4]: Contexto EXACTO enviado al LLM final: {messages_for_llm}")

    ans = answer_llm.invoke(messages_for_llm).content
    logger.debug(f"DEBUGGING [3/4]: Respuesta CRUDA recibida del LLM: {ans}")

    return {"messages": [AIMessage(content=ans)]}
