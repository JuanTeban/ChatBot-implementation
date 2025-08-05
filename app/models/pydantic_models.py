from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any

class ModelName(str, Enum):
    GPT4_1 = "llama-3.3-70b"
    GPT4_1_MINI = "llama-3.3-70b"

class QueryInput(BaseModel):
    question: str
    session_id: str = Field(default=None)
    model: ModelName = Field(default=ModelName.GPT4_1_MINI)

class ChartData(BaseModel):
    spec: Dict[str, Any]
    title: str
    download_id: str

class QueryResponse(BaseModel):
    answer: str
    session_id: str
    model: ModelName
    chart: Optional[ChartData] = None

class DocumentInfo(BaseModel):
    id: int
    filename: str
    upload_timestamp: datetime

class DeleteFileRequest(BaseModel):
    file_id: int