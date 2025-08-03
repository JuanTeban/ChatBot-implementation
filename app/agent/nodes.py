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
    # ✅ CORRECCIÓN 1: Darle memoria al router con el historial reciente
    recent_messages = state.get("messages", [])[-6:] if state.get("messages") else []
    conversation_context = ""
    if len(recent_messages) > 1:
        conversation_context = "### CONVERSACIÓN RECIENTE:\n"
        for msg in recent_messages:
            if isinstance(msg, HumanMessage):
                conversation_context += f"Usuario: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                conversation_context += f"Asistente: {msg.content}\n"

    # ✅ CORRECCIÓN 2: Prompt más inteligente que entiende el seguimiento
    system_prompt = f"""
    Eres un agente de clasificación experto. Tu tarea es analizar la última pregunta del usuario DENTRO DEL CONTEXTO de la conversación reciente y decidir la ruta correcta. Responde SOLO con el JSON correspondiente.

    {conversation_context}

    **Reglas de Enrutamiento:**
    1.  `sql`: Usa esta ruta si la pregunta del usuario requiere consultar la base de datos. Esto incluye:
        - Preguntas iniciales sobre datos ("¿cuántos hay?", "dame la lista de...").
        - Preguntas de seguimiento que piden más detalles sobre datos ya presentados ("dime cuales son", "y de esos, cuáles...", "muéstrame la lista").
    2.  `persona_answer`: Para preguntas sobre ti ("¿quién eres?").
    3.  `end`: Para saludos o despedidas simples ("hola", "gracias").
    4.  `answer`: SOLO si la pregunta es sobre el historial y NO requiere nuevos datos (ej: "¿qué te acabo de preguntar?").

    **Ejemplo CRÍTICO de seguimiento:**
    - CONVERSACIÓN RECIENTE:
      - Usuario: ¿Cuántos defectos reportó Angela?
      - Asistente: Reportó 11.
    - ÚLTIMA PREGUNTA DEL USUARIO: "dime cuales son"
    - TU JSON: {{"route": "sql"}} (Porque pide una lista, que requiere una nueva consulta)

    **ÚLTIMA PREGUNTA DEL USUARIO:**
    "{recent_messages[-1].content if recent_messages else ''}"
    """

    # Usar solo el prompt del sistema, ya que el contexto está dentro
    messages_for_llm = [SystemMessage(content=system_prompt)]
 
    try:
        result = router_llm.invoke(messages_for_llm)
        logger.info(f"Router decision: {result.route}")
        
        if result.route == "end" and result.reply:
            return {"messages": [AIMessage(content=result.reply)], "route": result.route}
        
        return {"route": result.route}
    
    except Exception as e:
        logger.error(f"Error in router_node: {e}")
        return {"route": "answer"}


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

    template = """
    Eres un experto en SQL y DuckDB. Tu tarea es generar consultas SQL precisas, consistentes y contextuales.

    **REGLAS CRÍTICAS DE GENERACIÓN:**
    1.  **CONSISTENCIA:** Para preguntas similares, usa SIEMPRE la misma lógica SQL.
    2.  **BÚSQUEDA EXACTA vs LIKE:** Para valores específicos como 'FINANCIERO', usa `= 'valor_exacto'`. Para búsquedas de nombres de personas, usa `UPPER()` y `LIKE`.
    3.  **FRENTES vs HALLAZGOS:** Distingue entre contar frentes (`COUNT(DISTINCT frente)`) y contar hallazgos (`COUNT(*)`).
    4.  **CONTEO vs LISTADO:** Para "¿cuántos?", usa `COUNT(*)`. Para "dime cuales", "lista", etc., usa `SELECT campos_especificos`.
    5.  **RESPUESTA DIRECTA:** Solo código SQL, sin explicaciones.

    ---
    **MANEJO DE CONTEXTO (MUY IMPORTANTE):**
    1.  **PRIORIZA LA PREGUNTA ACTUAL:** Si la "PREGUNTA EXACTA DEL USUARIO" es una pregunta completa y con sentido propio (ej: "Dime cuales estan en tratamiento", "cuantos defectos tiene el modulo TX"), **IGNORA** los filtros de la conversación anterior y genera una consulta nueva basada **SOLO** en la pregunta actual.
    2.  **USA CONTEXTO SOLO PARA AMBIGÜEDAD:** Si la "PREGUNTA EXACTA DEL USUARIO" es corta, incompleta o ambigua (ej: "dime cuales son", "y cuantos tiene?", "y los de ella?"), **ENTONCES Y SOLO ENTONCES**, mira el "CONTEXTO CONVERSACIONAL RECIENTE" para entender a qué se refiere y re-utilizar los filtros de la consulta anterior.
    ---

    **EJEMPLO DE MANEJO DE CONTEXTO:**
    - **Contexto:** Se acaba de hablar de los defectos de "Angela Patricia".
    - **Pregunta Actual:** "Dime cuales estan en tratamiento"
    - **Análisis:** La pregunta actual es completa. Se debe ignorar a "Angela Patricia".
    - **SQL Correcto:** `SELECT nombre_defecto, numero_defecto FROM tu_tabla WHERE estado_de_defecto = 'En tratamiento';`

    - **Contexto:** Se acaba de hablar de los defectos de "Angela Patricia".
    - **Pregunta Actual:** "y cuales son?"
    - **Análisis:** La pregunta es ambigua. Se debe usar el contexto de "Angela Patricia".
    - **SQL Correcto:** `SELECT nombre_defecto, numero_defecto FROM tu_tabla WHERE UPPER(autor_del_defecto) LIKE UPPER('%angela%patricia%') AND estado_de_defecto = 'En tratamiento';`

    {conversation_context}
    **CONTEXTO DE TABLAS DISPONIBLE:**
    {context}

    **PREGUNTA EXACTA DEL USUARIO:**
    {question}

    **CONSULTA SQL:**
    """
    prompt = PromptTemplate.from_template(template)
    try:
        llm_chain = prompt | answer_llm | StrOutputParser()
        sql_query = llm_chain.invoke(
            {
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
        logger.info(
            f"Conversation context included: {'Yes' if conversation_context else 'No'}"
        )
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
