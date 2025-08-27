# app/multimodal_rag/models.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any, List
from datetime import datetime

Modality = Literal["text", "table", "image"]

class ChunkMetadata(BaseModel):
    doc_id: str
    chunk_id: str
    responsable: Optional[str] = None
    defecto: Optional[str] = None
    element_type: Modality
    source_file: str
    source_path: str
    page: Optional[int] = None
    sha256: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class Evidence(BaseModel):
    """Representa un artefacto crudo listo para UI/LLM."""
    modality: Modality
    content_path: Optional[str] = None  # rutas en docstore para image o text/table crudo
    text: Optional[str] = None          # texto crudo o markdown de tabla
    html: Optional[str] = None          # tabla HTML (si aplica)
    summary: Optional[str] = None       # sumario para retrieval
    metadata: ChunkMetadata

class IngestionResult(BaseModel):
    responsable: str
    defecto: str
    processed_files: int
    chunks_indexed: int
    images_saved: int
    tables_saved: int
    texts_saved: int
