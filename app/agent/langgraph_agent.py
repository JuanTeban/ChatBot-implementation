from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langgraph.pregel import Pregel
from app.agent.nodes import (
    router_node, 
    rag_node, 
    answer_node,
    sql_context_node,
    sql_generation_node, 
    sql_execution_node
)
from app.agent.shared import AgentState
from app.utils.persistence import get_checkpointer

_agent: Optional[Pregel] = None

def get_agent() -> Pregel:
    global _agent
    if _agent is None:
        g = StateGraph(AgentState)
        
        # Add all nodes
        g.add_node("router", router_node)
        g.add_node("sql_context", sql_context_node)
        g.add_node("sql_generation", sql_generation_node)
        g.add_node("sql_execution", sql_execution_node)
        g.add_node("answer", answer_node)

        g.set_entry_point("router")
        
        g.add_conditional_edges(
            "router",
            from_router,
            {
                "sql": "sql_context",
                "answer": "answer",
                "end": END,
                "persona_answer": "answer"
            }
        )
        
        
        # SQL flow with conditional routing
        g.add_conditional_edges(
            "sql_context",
            from_sql_context,
            {
                "sql_generation": "sql_generation",
                "answer": "answer"
            }
        )
        
        g.add_conditional_edges(
            "sql_generation", 
            from_sql_generation,
            {
                "sql_execution": "sql_execution",
                "answer": "answer"
            }
        )
        
        g.add_conditional_edges(
            "sql_execution",
            from_sql_execution,
            {
                "sql_generation": "sql_generation",
                "answer": "answer"
            }
        )
        
        g.add_edge("answer", END)

        _agent = g.compile(checkpointer=get_checkpointer())
        print("✅ Agente SQL compilado exitosamente.")

    return _agent

def from_router(st: AgentState) -> Literal["sql", "answer", "end", "persona_answer"]:
    return st["route"]

def from_sql_context(st: AgentState) -> Literal["sql_generation", "answer"]:
    if st.get("sql_error"):
        return "answer"
    return "sql_generation"

def from_sql_generation(st: AgentState) -> Literal["sql_execution", "answer"]:
    if st.get("sql_error"):
        return "answer"
    return "sql_execution"

def from_sql_execution(st: AgentState) -> Literal["sql_generation", "answer"]:
    if st.get("sql_error"):
        retry_count = st.get("retry_count", 0)
        if retry_count < 1:
            return "sql_generation"
    return "answer"