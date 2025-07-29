from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agent.shared import AgentState, router_llm, answer_llm, RouteDecision
from app.tools.tools import rag_search_tool
from app.agent.persona import AGENT_PERSONA

def router_node(state: AgentState) -> dict:
    system_prompt = (
        "You are an expert classification agent. Your task is to analyze the user's last message and categorize it into one of the following routes. Respond ONLY with the corresponding JSON.\n\n"
        "**Available Routes:**\n"
        "1.  `persona_answer`: For questions about you, the AI assistant (e.g., 'who are you?', 'what can you do?').\n"
        "2.  `end`: For simple greetings, farewells, or acknowledgements (e.g., 'hello', 'thanks', 'ok').\n"
        "3.  `rag`: For specific questions seeking information on a topic, person, or event that would likely be in a knowledge base (e.g., 'what is JiraBuddy?', 'summarize the TME-Takomi report'). This is your default for information-seeking questions.\n"
        "4.  `answer`: For follow-up questions where the answer is likely already in the immediate chat history (e.g., 'what was my last question?', 'what did you just say?').\n\n"
        "**Examples:**\n"
        "- User message: 'Hola'\n- Your JSON response: {\"route\": \"end\", \"reply\": \"Hola, ¿en qué puedo ayudarte?\"}\n"
        "- User message: 'who are you?'\n- Your JSON response: {\"route\": \"persona_answer\"}\n"
        "- User message: 'Dime cual fue la solucion que propuso el equipo TME-Takomi TeamBE'\n- Your JSON response: {\"route\": \"rag\"}\n"
        "- User message: 'what did I just ask?'\n- Your JSON response: {\"route\": \"answer\"}"
    )
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    
    result: RouteDecision = None
    try:
        result = router_llm.invoke(messages)
    except Exception as e:
        print(f"--- ROUTER LLM ERROR ---: El LLM del router falló o devolvió un formato inválido. Error: {e}")
    
    if not result or not hasattr(result, 'route'):
        print(f"--- ROUTER LLM WARNING ---: El resultado fue inválido. Usando fallback seguro a 'rag' para intentar buscar información.")
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