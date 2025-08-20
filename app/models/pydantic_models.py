from pydantic import BaseModel, EmailStr
from datetime import datetime

class DocumentInfo(BaseModel):
    id: int
    filename: str
    upload_timestamp: datetime

class DeleteFileRequest(BaseModel):
    file_id: int

class Consultant(BaseModel):
    name: str
    email: EmailStr