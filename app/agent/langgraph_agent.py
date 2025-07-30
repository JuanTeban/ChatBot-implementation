from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langgraph.pregel import Pregel
from app.agent.nodes import router_node, rag_node, answer_node
from app.agent.sql_nodes import get_schema_node, query_generator_node, execute_query_node, sql_answer_node
from app.agent.shared import AgentState
from app.utils.persistence import get_checkpointer

_agent: Optional[Pregel] = None

def should_retry_sql(state: AgentState) -> Literal["generate_query", "generate_answer"]:
    if state.get("sql_error"):
        return "generate_query"
    return "generate_answer"

def get_agent() -> Pregel:
    global _agent
    if _agent is None:
        sql_workflow = StateGraph(AgentState)
        sql_workflow.add_node("get_schema", get_schema_node)
        sql_workflow.add_node("generate_query", query_generator_node)
        sql_workflow.add_node("execute_query", execute_query_node)
        sql_workflow.add_node("generate_answer", sql_answer_node)
        sql_workflow.set_entry_point("get_schema")
        sql_workflow.add_edge("get_schema", "generate_query")
        sql_workflow.add_edge("generate_query", "execute_query")
        sql_workflow.add_conditional_edges(
            "execute_query",
            should_retry_sql,
            {"generate_query": "generate_query", "generate_answer": "generate_answer"}
        )
        sql_workflow.add_edge("generate_answer", END)
        sql_agent_graph = sql_workflow.compile()

        g = StateGraph(AgentState)
        g.add_node("router", router_node)
        g.add_node("rag_lookup", rag_node)
        g.add_node("answer", answer_node)
        g.add_node("sql_agent", sql_agent_graph)
        g.set_entry_point("router")
        g.add_conditional_edges(
            "router",
            from_router,
            {
                "rag": "rag_lookup",
                "sql_query": "sql_agent",
                "answer": "answer",
                "end": END,
                "persona_answer": "answer"
            }
        )
        g.add_edge("rag_lookup", "answer")
        g.add_edge("answer", END)
        g.add_edge("sql_agent", END)
        _agent = g.compile(checkpointer=get_checkpointer())
        print("DEBUG: Agente compilado exitosamente en el primer uso.")
    return _agent

def from_router(st: AgentState) -> Literal["rag", "answer", "end", "persona_answer", "sql_query"]:
    return st["route"]