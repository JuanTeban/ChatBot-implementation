# app/agent/shared.py
from typing import TypedDict, List, Literal, Annotated
from operator import add
from pydantic import BaseModel, Field
from langchain_cerebras import ChatCerebras
from langchain_core.messages import BaseMessage

class RouteDecision(BaseModel):
    route: Literal["rag", "answer", "end", "persona_answer"]
    reply: str | None = Field(None, description="Filled only when route == 'end'")

router_llm = ChatCerebras(model="llama-3.3-70b", temperature=0)\
             .with_structured_output(RouteDecision)
answer_llm = ChatCerebras(model="llama-3.3-70b", temperature=0.2)

class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add]
    route:    Literal["rag", "answer", "end", "persona_answer"]
    rag:      str