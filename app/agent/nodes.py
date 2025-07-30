from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agent.shared import AgentState, router_llm, answer_llm, RouteDecision
from app.tools.tools import rag_search_tool
from app.agent.persona import AGENT_PERSONA
from app.utils.db_utils import get_document_type

def router_node(state: AgentState, config: dict) -> dict:
    source_id = state.get("source_id")
    
    # --- CAPA 0: ENRUTAMIENTO EXPLÍCITO Y ROBUSTO ---
    if source_id:
        print(f"DEBUG: Enrutador Explícito -> Verificando tipo para source_id: {source_id}")
        # Consultamos el tipo de documento en la base de datos
        doc_type = get_document_type(source_id)
        
        if doc_type == 'excel':
            return {"route": "sql_query"}
        elif doc_type == 'rag':
            # Corregimos el nombre de la ruta para que coincida con el grafo
            return {"route": "rag"}
        else:
            # Si el ID no se encuentra o no tiene tipo, se pasa al enrutador híbrido
            print(f"WARN: source_id {source_id} no encontrado o sin tipo, usando enrutador híbrido.")

    # --- CAPA 1: FILTRO RÁPIDO CON PALABRAS CLAVE DINÁMICAS ---
    last_message = state["messages"][-1].content.lower()
    # Ahora puede acceder a 'config' porque fue pasado como argumento
    sql_keywords = config["configurable"]["sql_keywords"]
    
    if any(keyword in last_message for keyword in sql_keywords):
        print("DEBUG: Enrutador Híbrido -> Decisión por palabra clave dinámica: sql_query")
        return {"route": "sql_query"}

    # --- CAPA 2: FILTRO INTELIGENTE (LLM CON CADENA DE PENSAMIENTO) ---
    print("DEBUG: Enrutador Híbrido -> No se encontraron palabras clave, usando LLM con CoT.")
    
    system_prompt = (
        "Eres un agente enrutador experto. Tu tarea es analizar el último mensaje del usuario y decidir qué ruta es la más apropiada. Para tomar tu decisión, primero debes escribir un 'Pensamiento' donde analices la pregunta y justifiques tu elección. Luego, en una nueva línea, escribe la respuesta final en formato JSON.\n\n"
        "**Rutas Disponibles:**\n"
        "1.  `sql_query`: Para cualquier pregunta cuya respuesta se encuentre ÚNICAMENTE dentro del conjunto de datos estructurado de 'defectos'.\n"
        "2.  `rag`: Para preguntas generales sobre temas o conceptos que NO están en el conjunto de datos de 'defectos'.\n"
        "3.  `persona_answer`: Para preguntas sobre ti, el asistente de IA.\n"
        "4.  `end`: Para saludos simples, despedidas o agradecimientos.\n"
        "5.  `answer`: Para preguntas de seguimiento sobre el historial inmediato.\n\n"
        "**Ejemplos de Cómo Pensar y Responder:**\n\n"
        "--- Ejemplo 1 ---\n"
        "Mensaje del usuario: 'háblame de la agilidad en el desarrollo'\n"
        "Pensamiento: El usuario pregunta por un concepto general ('agilidad') que no está en el dataset de defectos. La ruta es `rag`.\n"
        "Tu respuesta en JSON: {\"route\": \"rag\"}\n\n"
        "--- Ejemplo 2 ---\n"
        "Mensaje del usuario: '¿cuál es tu función principal?'\n"
        "Pensamiento: El usuario pregunta sobre mí, el asistente. La ruta es `persona_answer`.\n"
        "Tu respuesta en JSON: {\"route\": \"persona_answer\"}\n\n"
        "--- Ejemplo 3 ---\n"
        "Mensaje del usuario: 'gracias por la ayuda'\n"
        "Pensamiento: Es una despedida simple. La ruta es `end`.\n"
        "Tu respuesta en JSON: {\"route\": \"end\", \"reply\": \"De nada. ¡Que tengas un buen día!\"}"
    )
    
    messages_for_llm = [SystemMessage(content=system_prompt), state["messages"][-1]]
    
    result: RouteDecision = None
    try:
        result = router_llm.invoke(messages_for_llm)
    except Exception as e:
        print(f"--- ROUTER LLM ERROR ---: {e}")
        result = RouteDecision(route="rag", reply=None)

    if result.route == "end":
        reply = result.reply or "Claro, ¿hay algo más en lo que pueda ayudarte?"
        return {"messages": [AIMessage(content=reply)], "route": result.route}
    
    return {"route": result.route}

def rag_node(state: AgentState) -> dict:
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")
    
    chunks = rag_search_tool.invoke({"query": query})
    
    if not chunks or "RAG_ERROR" in chunks:
        return {"rag": None, "route": "answer"}
    
    return {"rag": chunks, "route": "answer"}

def answer_node(state: AgentState) -> dict:
    conversation_history = state["messages"]
    
    context_for_prompt = "No se encontró contexto externo relevante."
    if state.get("rag"):
        context_for_prompt = f"== Contexto de Documentos Internos ==\n{state['rag']}"
    
    system_prompt = f"""
    Eres un asistente de IA experto. Tu misión es responder a la última pregunta del usuario de la forma más precisa y útil posible, siguiendo un conjunto estricto de reglas.

    ### FUENTES DE INFORMACIÓN Y REGLAS DE PRIORIDAD:
    1.  **SOBRE TI MISMO (MÁXIMA PRIORIDAD):** Si la pregunta es sobre ti (quién eres, qué puedes hacer, tus límites), tu ÚNICA fuente de verdad es la sección 'CONSTITUCIÓN DEL AGENTE'. Ignora las otras fuentes para estas preguntas.
    2.  **CONTEXTO EXTERNO (ALTA PRIORIDAD):** Si la pregunta es sobre un tema específico del mundo, tu fuente de verdad principal es la sección 'CONTEXTO EXTERNO (RAG)'. Basa tu respuesta en esta información.
    3.  **HISTORIAL DE CHAT (CONTEXTO CONVERSACIONAL):** Utiliza SIEMPRE el historial para entender el diálogo, recordar datos clave mencionados por el usuario (como su nombre) y mantener la coherencia.

    ### REGLAS DE COMPORTAMIENTO:
    - **Sé Honesto:** Si ninguna fuente contiene la respuesta, admítelo claramente. No inventes.
    - **Respeta la Privacidad:** Puedes buscar información sobre figuras públicas (CEOs, artistas). NIEGA la búsqueda solo si se trata de información privada de personas no públicas.
    - **Idioma:** Responde siempre en español.

    ---
    ### CONSTITUCIÓN DEL AGENTE (Tu Identidad):
    {AGENT_PERSONA}
    ---
    ### CONTEXTO EXTERNO (RAG):
    {context_for_prompt}
    ---
    """

    messages_for_llm = [SystemMessage(content=system_prompt)] + conversation_history
    
    ans = answer_llm.invoke(messages_for_llm).content

    return {"messages": [AIMessage(content=ans)]}