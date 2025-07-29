from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langgraph.pregel import Pregel
from app.agent.nodes import router_node, rag_node, answer_node
from app.agent.shared import AgentState
from app.utils.persistence import get_checkpointer

_agent: Optional[Pregel] = None

def get_agent() -> Pregel:
    global _agent
    if _agent is None:
        g = StateGraph(AgentState)
        g.add_node("router", router_node)
        g.add_node("rag_lookup", rag_node)
        g.add_node("answer", answer_node)

        g.set_entry_point("router")
        g.add_conditional_edges(
            "router",
            from_router,
            {
                "rag": "rag_lookup",
                "answer": "answer",
                "end": END,
                "persona_answer": "answer"
            }
        )
        g.add_edge("rag_lookup",  "answer")
        g.add_edge("answer", END)

        _agent = g.compile(checkpointer=get_checkpointer())
        print("✅ DEBUG: Agente compilado exitosamente en el primer uso.")

    return _agent

def from_router(st: AgentState) -> Literal["rag", "answer", "end", "persona_answer"]:
    return st["route"]