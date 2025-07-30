from typing import TypedDict, List, Literal, Annotated, Optional
from operator import add
from pydantic import BaseModel, Field
from langchain_cerebras import ChatCerebras
from langchain_core.messages import BaseMessage
import sqlite3

class RouteDecision(BaseModel):
    route: Literal["rag", "answer", "end", "persona_answer", "sql_query"]
    reply: str | None = Field(None, description="Filled only when route == 'end'")

router_llm = ChatCerebras(model="llama-3.3-70b", temperature=0)\
             .with_structured_output(RouteDecision)
answer_llm = ChatCerebras(model="llama-3.3-70b", temperature=0.2)
sql_llm = ChatCerebras(model="llama-3.3-70b", temperature=0.0)

class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add]
    route:    Literal["rag", "answer", "end", "persona_answer", "sql_query"]
    rag:      str
    db_schema: str
    question: str
    sql_query: str
    sql_result: str
    sql_error: str
    source_id: Optional[str]