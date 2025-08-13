# app/agent/shared.py
from typing import TypedDict, List, Literal, Annotated, Dict, Any
from operator import add
from pydantic import BaseModel, Field
from langchain_cerebras import ChatCerebras
from langchain_core.messages import BaseMessage

class RouteDecision(BaseModel):
    route: Literal["answer", "end", "persona_answer", "sql", "chart"]
    reply: str | None = Field(None, description="Filled only when route == 'end'")

router_llm = ChatCerebras(model="llama-3.3-70b", temperature=0)\
             .with_structured_output(RouteDecision)
answer_llm = ChatCerebras(model="llama-3.3-70b", temperature=0.2)

# NUEVO: LLM para resumir memoria (determinista)
summarizer_llm = ChatCerebras(model="llama-3.3-70b", temperature=0)

class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add]
    route: Literal["answer", "end", "persona_answer", "sql", "chart"]
    sql_context: str
    sql_query: str
    sql_result: str
    sql_result_json: str | None
    sql_error: str
    retry_count: int
    chart_spec: Dict[str, Any] | None
    chart_error: str | None

    # NUEVO: resumen acumulado de la conversación
    summary: str
