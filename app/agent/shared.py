from typing import TypedDict, List, Literal
from pydantic import BaseModel, Field
from langchain_cerebras import ChatCerebras
from langchain_core.messages import BaseMessage

# ── Pydantic schemas ─────────────────────────────────────────────────
class RouteDecision(BaseModel):
    route: Literal["rag", "answer", "end"]
    reply: str | None = Field(None, description="Filled only when route == 'end'")

class RagJudge(BaseModel):
    sufficient: bool

# ── LLM instances with structured output where needed ───────────────
router_llm = ChatCerebras(model="llama-3.3-70b", temperature=0)\
             .with_structured_output(RouteDecision)
judge_llm  = ChatCerebras(model="llama-3.3-70b", temperature=0)\
             .with_structured_output(RagJudge)
answer_llm = ChatCerebras(model="llama-3.3-70b", temperature=0.2)

# ── Shared state type ────────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    messages: List[BaseMessage]
    route:    Literal["rag", "answer", "end"]
    rag:      str
    web:      str 