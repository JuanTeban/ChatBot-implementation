from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.agent.shared import AgentState, router_llm, judge_llm, answer_llm, RouteDecision, RagJudge
from app.tools.tools import rag_search_tool, web_search_tool


def router_node(state: AgentState) -> AgentState:

    system_prompt = (
        "You are a master router AI. Your job is to decide the best course of action to respond to a user's query based on the conversation history.\n"
        "You have the following options:\n"
        "- 'end': Use this for simple greetings, farewells, or conversational pleasantries (e.g., 'hello', 'thank you', 'how are you?'). Provide a suitable 'reply' in Spanish.\n"
        "- 'rag': Use this if the user is asking a question that can likely be answered by your internal knowledge base. This is your primary source of information.\n"
        "- 'answer': Use this if you are confident you can answer the question directly from the conversation history without needing to look up information.\n"
        "Analyze the latest user message in the context of the entire conversation."
    )
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    result: RouteDecision = router_llm.invoke(messages)

    out = {"messages": state["messages"], "route": result.route}
    if result.route == "end":
        out["messages"] = state["messages"] + [AIMessage(content=result.reply or "Hello!")]
    return out

# ── Node 2: RAG lookup ───────────────────────────────────────────────
def rag_node(state: AgentState) -> AgentState:
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")

    chunks = rag_search_tool.invoke({"query": query})

    route_decision = "web" if not chunks or "RAG_ERROR" in chunks else "answer"

    return {
        **state,
        "rag": chunks,
        "route": route_decision
    }

"""
def rag_node(state: AgentState) -> AgentState:
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")

    chunks = rag_search_tool.invoke({"query": query})

    judge_messages = [
        ("system", (
        "You are a pragmatic judge. Your role is to determine if the retrieved information is relevant to the user's question. You don't need a perfect match, just a strong indication that the context is on the right track.\n"
        "If the information contains keywords or concepts from the user's question, it's likely sufficient.\n"
        "Respond ONLY with a JSON object: {\"sufficient\": true} or {\"sufficient\": false}."
        )),
        ("user", f"Question: {query}\n\nRetrieved info: {chunks}\n\nIs this sufficient to answer the question?")
    ]

    verdict: RagJudge = judge_llm.invoke(judge_messages)

    # Manejo seguro de errores
    if verdict is None or not hasattr(verdict, 'sufficient'):
        import logging
        logging.error(f"RAG_JUDGE_ERROR: verdict is None or missing 'sufficient'. Value: {verdict}")
        return {
            **state,
            "rag": chunks,
            "route": "web"
        }

    return {
        **state,
        "rag": chunks,
        "route": "answer" if verdict.sufficient else "web"
    }
"""

# ── Node 3: web search ───────────────────────────────────────────────
def web_node(state: AgentState) -> AgentState:
    query = next((m.content for m in reversed(state["messages"])
                  if isinstance(m, HumanMessage)), "")
    snippets = web_search_tool.invoke({"query": query})
    return {**state, "web": snippets, "route": "answer"}

# ── Node 4: final answer ─────────────────────────────────────────────
def answer_node(state: AgentState) -> AgentState:
    user_q = next((m.content for m in reversed(state["messages"])
                   if isinstance(m, HumanMessage)), "")

    ctx_parts = []
    if state.get("rag"):
        ctx_parts.append("Knowledge Base Information:\n" + state["rag"])
    if state.get("web"):
        ctx_parts.append("Web Search Results:\n" + state["web"])

    context = "\n\n".join(ctx_parts) if ctx_parts else "No external context available."

    prompt = f"""Eres un asistente de IA experto, amigable y profesional. Tu tarea es responder a la pregunta del usuario de la manera más precisa y útil posible, utilizando el contexto proporcionado.

    Question from user: {user_q}

    Context provided:
    {context}

    **Instrucciones:**
    1.  **Sintetiza la Información:** Combina la información de la base de conocimientos y la búsqueda web (si está disponible) para dar una respuesta completa.
    2.  **Tono Profesional:** Mantén un tono cordial y profesional en todo momento.
    3.  **Respuesta Directa:** Responde directamente a la pregunta del usuario.
    4.  **Si no hay contexto:** Si no tienes información suficiente en el contexto para responder, indícalo amablemente y sugiere al usuario que podría reformular la pregunta. No inventes información.
    5.  **Idioma:** Responde siempre en español."""
    messages = state["messages"] + [HumanMessage(content=prompt)]
    ans = answer_llm.invoke(messages).content

    return {
        **state,
        "messages": state["messages"] + [AIMessage(content=ans)]
    }