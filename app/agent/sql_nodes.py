import json
import re
from typing import Dict
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from app.agent.shared import AgentState, sql_llm, answer_llm
from app.tools.sql_tools import get_db_schema, execute_sql_query, get_distinct_column_values

def get_schema_node(state: AgentState, config: dict) -> Dict:
    conn = config["configurable"]["db_conn"]
    schema = get_db_schema.invoke({"conn": conn})
    return {"db_schema": schema}

def _clean_sql_query(query: str) -> str:
    """Extrae la consulta SQL de un bloque de código o texto."""
    match = re.search(r"```sql\s*(.*?)\s*```", query, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"SELECT.*", query, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return query.strip()

def query_generator_node(state: AgentState) -> Dict:
    schema = state["db_schema"]
    system_prompt = f"""Tu tarea es traducir la última pregunta del usuario a una consulta SQL sintácticamente correcta para SQLite. Usa el historial de chat previo para tener contexto si es necesario. Responde únicamente con el código SQL. No añadas explicaciones.
    Reglas:
    - Usa únicamente las tablas y columnas del esquema proporcionado.
    - Para buscar texto dentro de una columna (como nombres de personas o descripciones de defectos), utiliza el operador `LIKE` con comodines `%`. Por ejemplo, para buscar 'MONICA PATRICIA', usa `WHERE autor_del_defecto LIKE '%MONICA PATRICIA%'`.
    - NUNCA generes consultas que modifiquen la base de datos (solo SELECT).
    Esquema: {schema}"""

    messages_for_llm = [SystemMessage(content=system_prompt)] + state["messages"]

    if state.get("sql_error"):
        error_msg = f"El intento anterior falló con el error: {state['sql_error']}. Por favor, corrige la consulta SQL y vuelve a intentarlo."
        messages_for_llm.append(HumanMessage(content=error_msg))

    raw_query = sql_llm.invoke(messages_for_llm).content
    cleaned_query = _clean_sql_query(raw_query)
    return {"sql_query": cleaned_query}

def execute_query_node(state: AgentState, config: dict) -> Dict:
    query = state["sql_query"]
    conn = config["configurable"]["db_conn"]
    try:
        result = execute_sql_query.invoke({"conn": conn, "query": query})
        result_str = json.dumps(result, indent=2, ensure_ascii=False)
        return {"sql_result": result_str, "sql_error": None}
    except Exception as e:
        return {"sql_result": None, "sql_error": str(e)}

def sql_answer_node(state: AgentState) -> Dict:
    question = state["messages"][-1].content
    sql_result = state["sql_result"]
    system_prompt = f"""Eres un asistente de IA. Responde a la pregunta del usuario basándote en los datos proporcionados, en español.
Pregunta: {question}
Datos de la Base de Datos: {sql_result}"""
    messages = [SystemMessage(content=system_prompt)]
    final_answer = answer_llm.invoke(messages).content
    return {"messages": [AIMessage(content=final_answer)]}