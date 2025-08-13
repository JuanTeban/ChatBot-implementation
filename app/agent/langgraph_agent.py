from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langgraph.pregel import Pregel
from app.agent.nodes import (
    memory_guard_node,
    router_node,
    answer_node,
    sql_context_node,
    sql_generation_node, 
    sql_execution_node,
    chart_generation_node
)
from app.agent.shared import AgentState
from app.utils.persistence import get_checkpointer

_agent: Optional[Pregel] = None

def from_sql_execution_router(st: AgentState) -> Literal["chart_generation", "answer", "sql_generation"]:
    if st.get("sql_error"):
        retry_count = st.get("retry_count", 0)
        if retry_count < 1:
            return "sql_generation"
        return "answer"

    if st.get("route") == "chart":
        return "chart_generation"
    else:
        return "answer"

def get_agent() -> Pregel:
    global _agent
    if _agent is None:
        g = StateGraph(AgentState)
        
        g.add_node("memory_guard", memory_guard_node)
        g.add_node("router", router_node)
        g.add_node("sql_context", sql_context_node)
        g.add_node("sql_generation", sql_generation_node)
        g.add_node("sql_execution", sql_execution_node)
        g.add_node("chart_generation", chart_generation_node)
        g.add_node("answer", answer_node)

        g.set_entry_point("memory_guard")
        g.add_edge("memory_guard", "router")
        
        g.add_conditional_edges(
            "router",
            lambda st: st["route"],
            {
                "sql": "sql_context",
                "chart": "sql_context",
                "answer": "answer",
                "end": END,
                "persona_answer": "answer"
            }
        )
        
        g.add_conditional_edges(
            "sql_context",
            lambda st: "answer" if st.get("sql_error") else "sql_generation",
            {"sql_generation": "sql_generation", "answer": "answer"}
        )
        
        g.add_conditional_edges(
            "sql_generation", 
            lambda st: "answer" if st.get("sql_error") else "sql_execution",
            {"sql_execution": "sql_execution", "answer": "answer"}
        )
        
        g.add_conditional_edges(
            "sql_execution",
            from_sql_execution_router,
            {
                "sql_generation": "sql_generation",
                "chart_generation": "chart_generation",
                "answer": "answer"
            }
        )
        
        g.add_conditional_edges(
            "chart_generation",
            lambda st: "answer", # Siempre va a answer, incluso con error
            {"answer": "answer"}
        )
        
        g.add_edge("answer", END)

        _agent = g.compile(checkpointer=get_checkpointer())
        print("✅ Agente con soporte de gráficos (versión optimizada) compilado exitosamente.")

    return _agent