import os
from typing import Literal, List
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END

class AgentState(dict):
    messages: List[BaseMessage]
    route: Literal["rag", "answer", "end", "web"]

def router_node(state: AgentState) -> AgentState:
    return state

def rag_node(state: AgentState) -> AgentState:
    return state

def web_node(state: AgentState) -> AgentState:
    return state

def answer_node(state: AgentState) -> AgentState:
    return state

def from_router(st: AgentState) -> Literal["rag", "answer", "end"]:
    return st.get("route", "end")

def after_rag(st: AgentState) -> Literal["answer", "web"]:
    return st.get("route", "answer")

def after_web(_) -> Literal["answer"]:
    return "answer"

g = StateGraph(AgentState)
g.add_node("router", router_node)
g.add_node("rag_lookup", rag_node)
g.add_node("web_search", web_node)
g.add_node("answer", answer_node)

g.set_entry_point("router")
g.add_conditional_edges("router", from_router, {
    "rag": "rag_lookup", 
    "answer": "answer", 
    "end": END
})
g.add_conditional_edges("rag_lookup", after_rag, {
    "answer": "answer", 
    "web": "web_search"
})
g.add_edge("web_search",  "answer")
g.add_edge("answer", END)

agent = g.compile()

try:
    output_filename = "mi_grafo_agente.png"
    png_image = agent.get_graph().draw_mermaid_png()

    with open(output_filename, "wb") as f:
        f.write(png_image)
    
    full_path = os.path.abspath(output_filename)
    print(f"\nGráfico guardado exitosamente en: {full_path}\n")

except Exception as e:
    print(f"\nError al generar la imagen: {e}")
    print("Asegúrate de haber ejecutado los comandos de instalación.")

