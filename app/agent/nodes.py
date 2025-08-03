from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.agent.shared import AgentState, router_llm, answer_llm, RouteDecision
from app.tools.tools import rag_search_tool, sql_context_retriever, execute_duckdb_query, get_available_tables
from app.agent.persona import AGENT_PERSONA
import logging
import re

logger = logging.getLogger(__name__)

def router_node(state: AgentState) -> dict:
    system_prompt = (
        "You are an expert classification agent. Your task is to analyze the user's last message and categorize it into one of the following routes. Respond ONLY with the corresponding JSON.\n\n"
        "**Available Routes:**\n"
        "1. `persona_answer`: For questions about you, the AI assistant (e.g., 'who are you?', 'what can you do?').\n"
        "2. `end`: For simple greetings, farewells, or acknowledgements (e.g., 'hello', 'thanks', 'ok').\n"
        "3. `sql`: For questions that require querying a database, asking for data analysis, statistics, reports, or information that would be stored in tables (e.g., 'show me sales data', 'how many users do we have?', 'what are the top products?').\n"
        "4. `answer`: For follow-up questions where the answer is likely already in the immediate chat history (e.g., 'what was my last question?', 'what did you just say?').\n\n"
        "**Examples:**\n"
        "- User message: 'Hola'\n- Your JSON response: {\"route\": \"end\", \"reply\": \"Hola, ¿en qué puedo ayudarte?\"}\n"
        "- User message: 'who are you?'\n- Your JSON response: {\"route\": \"persona_answer\"}\n"
        "- User message: 'Cuántos registros tenemos en la base de datos?'\n- Your JSON response: {\"route\": \"sql\"}\n"
        "- User message: 'what did I just ask?'\n- Your JSON response: {\"route\": \"answer\"}"
    )
    
    last_message = state["messages"][-1]
    messages = [SystemMessage(content=system_prompt), last_message]
    
    try:
        result = router_llm.invoke(messages)
        logger.info(f"Router decision: {result.route}")
        
        if result.route == "end" and result.reply:
            return {"messages": [AIMessage(content=result.reply)], "route": result.route}
        
        return {"route": result.route}
    
    except Exception as e:
        logger.error(f"Error in router_node: {e}")
        return {"route": "answer"}
    """	
    system_prompt = (
        "You are an expert classification agent. Your task is to analyze the user's last message and categorize it into one of the following routes. Respond ONLY with the corresponding JSON.\n\n"
        "**Available Routes:**\n"
        "1. `persona_answer`: For questions about you, the AI assistant (e.g., 'who are you?', 'what can you do?').\n"
        "2. `end`: For simple greetings, farewells, or acknowledgements (e.g., 'hello', 'thanks', 'ok').\n"
        "3. `sql`: For questions that require querying a database, asking for data analysis, statistics, reports, or information that would be stored in tables (e.g., 'show me sales data', 'how many users do we have?', 'what are the top products?').\n"
        "4. `rag`: For specific questions seeking information on topics, documents, or general knowledge that would be in a knowledge base (e.g., 'what is JiraBuddy?', 'summarize the TME-Takomi report').\n"
        "5. `answer`: For follow-up questions where the answer is likely already in the immediate chat history (e.g., 'what was my last question?', 'what did you just say?').\n\n"
        "**Examples:**\n"
        "- User message: 'Hola'\n- Your JSON response: {\"route\": \"end\", \"reply\": \"Hola, ¿en qué puedo ayudarte?\"}\n"
        "- User message: 'who are you?'\n- Your JSON response: {\"route\": \"persona_answer\"}\n"
        "- User message: 'Cuántos registros tenemos en la base de datos?'\n- Your JSON response: {\"route\": \"sql\"}\n"
        "- User message: 'Muéstrame los 10 principales defectos por estado'\n- Your JSON response: {\"route\": \"sql\"}\n"
        "- User message: 'Dime cual fue la solucion que propuso el equipo TME-Takomi TeamBE'\n- Your JSON response: {\"route\": \"rag\"}\n"
        "- User message: 'what did I just ask?'\n- Your JSON response: {\"route\": \"answer\"}"
    )
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    
    result: RouteDecision = None
    try:
        result = router_llm.invoke(messages)
        logger.info(f"Router decision: {result.route}")
        
        if result.route == "end" and result.reply:
            return {"messages": [AIMessage(content=result.reply)], "route": result.route}
        
        return {"route": result.route}
    
    except Exception as e:
        logger.error(f"Error in router_node: {e}")
        return {"route": "answer"}
    """

def rag_node(state: AgentState) -> dict:
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")
    
    chunks = rag_search_tool.invoke({"query": query})
    
    if not chunks or "RAG_ERROR" in chunks:
        return {"rag": None, "route": "answer"}

    return {"rag": chunks, "route": "answer"}

def sql_context_node(state: AgentState) -> dict:
    """Retrieves relevant database context for SQL generation."""
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")
    
    context = sql_context_retriever.invoke({"query": query})
    
    if "SQL_ERROR" in context:
        return {"sql_context": None, "sql_error": context, "route": "answer"}
    
    logger.info("SQL context retrieved successfully")
    return {"sql_context": context, "route": "sql_generation"}

def sql_generation_node(state: AgentState) -> dict:
    user_question = next((m.content for m in reversed(state["messages"])
                          if isinstance(m, HumanMessage)), "")

    # ✅ NUEVA CORRECCIÓN: Agregar contexto conversacional reciente
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
    
    template = """
    Eres un experto en SQL y DuckDB. Tu tarea es generar consultas SQL precisas y CONSISTENTES.

    **REGLAS CRÍTICAS DE GENERACIÓN:**
    1.  **CONSISTENCIA:** Para preguntas similares, usa SIEMPRE la misma lógica SQL.
    2.  **BÚSQUEDA EXACTA vs LIKE:**
       - Para valores específicos como 'FINANCIERO', 'NO FINANCIERO': usa `= 'valor_exacto'`
       - Para búsquedas de nombres de personas: usa `UPPER() y LIKE`
    3.  **FRENTES vs HALLAZGOS:**
       - "¿Cuántos frentes son X?" → `SELECT COUNT(DISTINCT frente) WHERE frente = 'X'`
       - "¿Cuántos hallazgos son del frente X?" → `SELECT COUNT(*) WHERE frente = 'X'`
    4.  **VALORES EXACTOS DE FRENTE:**
       - 'FINANCIERO' (no usar LIKE para evitar capturar 'NO FINANCIERO')
       - 'NO FINANCIERO'
       - 'TECNICO'
       - 'ET'
    5.  **RESPUESTA DIRECTA:** Solo código SQL, sin explicaciones.

    **EJEMPLOS ESPECÍFICOS:**

    - **Pregunta:** "¿Cuántos frentes son financieros?"
    - **SQL Correcto:** `SELECT COUNT(DISTINCT frente) FROM tabla WHERE frente = 'FINANCIERO';`
    - **❌ INCORRECTO:** `SELECT COUNT(*) WHERE LIKE '%FINANCIERO%'` (cuenta hallazgos + captura NO FINANCIERO)

    - **Pregunta:** "¿Cuántos hallazgos son del frente financiero?"
    - **SQL Correcto:** `SELECT COUNT(*) FROM tabla WHERE frente = 'FINANCIERO';`

    - **Pregunta:** "De los defectos de LINA MARIA, cuántos están en estado nuevo?"
    - **SQL Correcto:** `SELECT COUNT(*) FROM tabla WHERE UPPER(autor) LIKE UPPER('%lina%maria%') AND estado = 'Nuevo';`

    **PREGUNTAS DE SEGUIMIENTO:**
    - Si hay contexto conversacional, mantén CONSISTENCIA con consultas anteriores
    - Si antes usaste `frente = 'FINANCIERO'`, sigue usándolo, no cambies a LIKE

    {conversation_context}**CONTEXTO DE TABLAS DISPONIBLE:**
    {context}

    **PREGUNTA EXACTA DEL USUARIO:**
    {question}

    **CONSULTA SQL:**
    """
    
    prompt = PromptTemplate.from_template(template)
    
    try:
        llm_chain = prompt | answer_llm | StrOutputParser()
        sql_query = llm_chain.invoke({
            "context": context,
            "question": user_question,
            "conversation_context": conversation_context
        })
        
        sql_query = sql_query.strip()
        sql_query = re.sub(r'```sql\n?', '', sql_query)
        sql_query = re.sub(r'```\n?', '', sql_query)
        sql_query = sql_query.strip()
        
        logger.info(f"Generated SQL query: {sql_query}")
        logger.info(f"Conversation context included: {'Yes' if conversation_context else 'No'}")
        return {"sql_query": sql_query, "route": "sql_execution"}
        
    except Exception as e:
        logger.error(f"Error generating SQL: {e}")
        return {"sql_error": f"Error generating SQL query: {str(e)}", "route": "answer"}
    

def sql_execution_node(state: AgentState) -> dict:
    """Executes the generated SQL query."""
    
    sql_query = state.get("sql_query", "")
    
    if not sql_query:
        return {"sql_error": "No SQL query to execute", "route": "answer"}
    
    
    result = execute_duckdb_query.invoke({"sql_query": sql_query})
    
    if result.startswith("SQL_ERROR"):
       
        return {"sql_error": result, "route": "answer"}
    
    logger.info("SQL query executed successfully")
    return {"sql_result": result, "route": "answer"}

def answer_node(state: AgentState) -> dict:
    """Genera la respuesta final al usuario basándose en el estado del agente."""

    # --- Log de Depuración Nivel 1: ¿Qué entra al nodo? ---
    print("\n\n" + "="*60)
    print("🕵️  DEBUGGING [1/4]: Estado de entrada del `answer_node`")
    print(f"  - ¿Resultado SQL presente?: {'✅ Sí' if state.get('sql_result') else '❌ No'}")
    print(f"    - Contenido: {state.get('sql_result', 'N/A')}")
    print(f"  - ¿Error SQL presente?: {'✅ Sí' if state.get('sql_error') else '❌ No'}")
    print(f"    - Contenido: {state.get('sql_error', 'N/A')}")
    print(f"  - ¿Consulta SQL ejecutada?: {'✅ Sí' if state.get('sql_query') else '❌ No'}")
    print(f"    - Consulta: {state.get('sql_query', 'N/A')}")
    print(f"  - Longitud del historial de chat: {len(state.get('messages', []))} mensajes")
    print("="*60)

    # ✅ CORRECCIÓN 1: Extraer la pregunta original del usuario correctamente
    user_question = next((m.content for m in reversed(state["messages"])
                          if isinstance(m, HumanMessage)), "")
    
    # ✅ NUEVA CORRECCIÓN: Extraer contexto conversacional reciente (últimos 6 mensajes)
    recent_messages = state.get("messages", [])[-6:] if state.get("messages") else []
    conversation_context = ""
    
    if len(recent_messages) > 1:  # Si hay más de un mensaje, incluir contexto
        conversation_context = "\n### CONTEXTO DE CONVERSACIÓN RECIENTE:\n"
        for i, msg in enumerate(recent_messages[:-1]):  # Excluir el último (pregunta actual)
            if isinstance(msg, HumanMessage):
                conversation_context += f"👤 Usuario: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                conversation_context += f"🤖 Asistente: {msg.content}\n"
        conversation_context += "\n"
    
    # ✅ CORRECCIÓN 2: Incluir la consulta SQL ejecutada para dar contexto
    sql_query_context = ""
    if state.get("sql_query"):
        sql_query_context = f"### CONSULTA SQL EJECUTADA:\n```sql\n{state.get('sql_query')}\n```\n\n"
    
    context_for_prompt = "No se encontró información relevante."
    
    if state.get("sql_result"):
        sql_result = state.get("sql_result", "").replace("QUERY_RESULT::", "").strip()
        context_for_prompt = f"{sql_query_context}### RESULTADOS DE LA CONSULTA ACTUAL:\n{sql_result}"
    elif state.get("sql_error"):
        context_for_prompt = f"{sql_query_context}### ERROR EN LA CONSULTA ACTUAL:\n{state.get('sql_error')}"

    # ✅ CORRECCIÓN 3: Prompt mejorado con contexto conversacional
    system_prompt = f"""
    Eres un asistente de IA experto en análisis de datos. Tu objetivo es responder la pregunta específica del usuario usando los datos obtenidos y el contexto de la conversación.

    ### PREGUNTA ACTUAL DEL USUARIO:
    "{user_question}"

    ### REGLAS DE RESPUESTA:
    1.  **Responde directamente:** Los datos que recibes son la respuesta EXACTA a la pregunta del usuario.
    2.  **Usa contexto conversacional:** Si el usuario hace preguntas de seguimiento (como "¿y cuántos tiene?"), usa la conversación reciente para entender a qué se refiere.
    3.  **Interpreta en contexto:** Si ves `count_star() 11` y los datos filtran por algo específico, entonces esos 11 son específicamente para esa consulta.
    4.  **Sé conversacional y natural:** Responde como si estuvieras hablando con un colega, sin mencionar aspectos técnicos.
    5.  **Idioma:** Responde siempre en español.
    6.  **Formato:** Usa **negritas** para resaltar datos clave.

    ### MANEJO DE PREGUNTAS DE SEGUIMIENTO:
    - Si el usuario pregunta "¿cuántos tiene?" revisa la conversación reciente para saber de qué está hablando
    - Si no hay datos SQL actuales pero hay contexto conversacional, explica que necesitas más información
    - Mantén coherencia con respuestas anteriores

    ### EJEMPLOS DE RESPUESTAS NATURALES:
    - **Pregunta:** "¿Qué módulo tiene más hallazgos?"
    - **Datos:** `modulo: TX, count: n`
    - **Respuesta:** "El módulo **TX** es el que tiene más hallazgos reportados, con **n** hallazgos."
    ### EJEMPLOS DE RESPUESTAS DE SEGUIMIENTO:
    - **Pregunta de seguimiento:** "¿y cuántos tiene?"
    - **Contexto:** Conversación anterior sobre módulo TX
    - **Respuesta:** "El módulo **TX** tiene **n** hallazgos reportados."

    ---
    ### CONSTITUCIÓN DEL AGENTE:
    {AGENT_PERSONA}
    ---
    {conversation_context}### INFORMACIÓN DISPONIBLE PARA LA CONSULTA ACTUAL:
    {context_for_prompt}
    ---
    
    IMPORTANTE: Si la pregunta actual es de seguimiento y no hay nuevos datos SQL, usa el contexto conversacional para responder coherentemente.
    """

    # ✅ CORRECCIÓN 4: Incluir contexto conversacional en los mensajes para el LLM
    # Enviamos más contexto pero mantenemos la pregunta actual clara
    user_message = HumanMessage(content=f"Basándote en los datos actuales y el contexto conversacional, responde: {user_question}")
    messages_for_llm = [SystemMessage(content=system_prompt), user_message]

    # --- Log de Depuración Nivel 2: ¿Qué se le envía al LLM? ---
    print("\n" + "="*60)
    print("🕵️  DEBUGGING [2/4]: Contexto EXACTO enviado al LLM final")
    print(f"PREGUNTA EXTRAÍDA: {user_question}")
    print(f"CONSULTA SQL DISPONIBLE: {state.get('sql_query', 'N/A')}")
    print(f"MENSAJES RECIENTES: {len(recent_messages)} mensajes incluidos")
    print("PROMPT COMPLETO:")
    print(messages_for_llm[0].content)
    print("="*60)

    # Invocamos al LLM
    ans = answer_llm.invoke(messages_for_llm).content

    # --- Log de Depuración Nivel 3: ¿Qué respondió el LLM? ---
    print("\n" + "="*60)
    print("🕵️  DEBUGGING [3/4]: Respuesta CRUDA recibida del LLM")
    print(ans)
    print("="*60)

    # --- Log de Depuración Nivel 4: Estado completo para memoria ---
    print("\n" + "="*60)
    print("🕵️  DEBUGGING [4/4]: Estado completo disponible")
    print(f"- user_question: {user_question}")
    print(f"- sql_query: {state.get('sql_query', 'N/A')}")
    print(f"- sql_result: {state.get('sql_result', 'N/A')}")
    print(f"- sql_error: {state.get('sql_error', 'N/A')}")
    print(f"- route: {state.get('route', 'N/A')}")
    print(f"- recent_messages_count: {len(recent_messages)}")
    print("="*60 + "\n\n")

    return {"messages": [AIMessage(content=ans)]}
