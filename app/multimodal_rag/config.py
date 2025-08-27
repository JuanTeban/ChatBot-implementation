# app/multimodal_rag/config.py
from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from chromadb import PersistentClient
from chromadb.utils import embedding_functions

# Importa tu settings real - CORREGIDO
from app.config.settings import (
    GEMINI_API_KEY,
    DATA_STORE_PATH, VECTOR_STORE_DIR, DOCSTORE_PATH,
    MULTIMODAL_COLLECTION, MULTIMODAL_INPUT_ROOT,
    EMBEDDING_MODEL_NAME, VISION_MODEL,
    ENABLE_RATE_LIMITING, MAX_CONCURRENT_LLM_CALLS, LLM_REQUEST_DELAY,
)

# --- Logging global (DEBUG detallado) ---
LOG_FORMAT = "[%(levelname)s] %(asctime)s %(name)s :: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger("mmrag.config")

# Validaciones básicas
if not MULTIMODAL_INPUT_ROOT:
    log.warning("MULTIMODAL_INPUT_ROOT no está definido en .env; usa --root en CLI.")

# --- Cliente Chroma persistente (tu instancia en disco) ---
def get_chroma_collection():
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    log.debug(f"Inicializando Chroma en: {VECTOR_STORE_DIR}")
    client = PersistentClient(path=str(VECTOR_STORE_DIR))
    try:
        col = client.get_collection(MULTIMODAL_COLLECTION)
        log.debug(f"Colección existente encontrada: {MULTIMODAL_COLLECTION}")
    except Exception:
        log.debug(f"Colección no existe; creando: {MULTIMODAL_COLLECTION}")
        col = client.create_collection(
            name=MULTIMODAL_COLLECTION,
            metadata={"purpose": "multimodal_evidence"}
        )
    return col

# --- Embeddings (Gemini) ---
# Recomendado: usar Gemini Embeddings vía API oficial
# Docs API: https://ai.google.dev/api/embeddings ; Guía: https://ai.google.dev/gemini-api/docs/embeddings
class GeminiEmbedder:
    def __init__(self, model_name: str):
        self.model = model_name  # p.ej., "text-embedding-004" o "gemini-embedding-001"
        self.api_key = GEMINI_API_KEY
        if not self.api_key:
            log.warning("GEMINI_API_KEY no configurada; embedder no funcionará.")
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._genai = genai
        except Exception as e:
            log.exception("No se pudo importar google.generativeai: %s", e)
            self._genai = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._genai:
            raise RuntimeError("Gemini no inicializado; instala `google-generativeai` y setea GEMINI_API_KEY.")
        
        # Filtrar textos vacíos primero
        valid_texts = [t.strip() for t in texts if t and t.strip()]
        if not valid_texts:
            log.warning("Todos los textos están vacíos, devolviendo lista vacía")
            return []
        
        try:
            # Para textos individuales, procesar uno por uno
            embeddings = []
            for text in valid_texts:
                resp = self._genai.embed_content(
                    model=self.model,
                    content=text,  # ✅ UNO A LA VEZ
                    task_type="RETRIEVAL_DOCUMENT"
                )
                # ✅ FORMATO CORRECTO
                embedding = resp["embedding"]
                embeddings.append(embedding)
            
            log.debug(f"Embeddings generados: {len(embeddings)} items, dim={len(embeddings[0]) if embeddings else 'NA'}")
            return embeddings
        except Exception as e:
            log.error(f"Error generando embeddings: {e}")
            raise RuntimeError(f"Fallo en el embedder: {e}")

def get_text_embedder() -> GeminiEmbedder:
    # Usa tu nombre de modelo desde settings (antes "models/embedding-001"; hoy se recomienda "text-embedding-004" o "gemini-embedding-001")
    # Docs: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/text-embeddings-api
    model = EMBEDDING_MODEL_NAME or "text-embedding-004"
    return GeminiEmbedder(model_name=model)

# --- Modelo de visión (para resumir imágenes con Gemini) ---
class GeminiVision:
    def __init__(self, model_name: str):
        self.api_key = GEMINI_API_KEY
        self.model_name = model_name
        if not self.api_key:
            log.warning("GEMINI_API_KEY no configurada; visión no funcionará.")
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(model_name)
        except Exception as e:
            log.exception("No se pudo inicializar Gemini visión: %s", e)
            self._model = None

    def describe_image(self, pil_image, prompt: str) -> str:
        """Devuelve un caption detallado para recuperación (no para UI)."""
        if not self._model:
            raise RuntimeError("Gemini visión no inicializado.")
        # Guía: https://ai.google.dev/gemini-api/docs/image-understanding
        try:
            resp = self._model.generate_content([prompt, pil_image])
            text = getattr(resp, "text", None) or ""
            return text.strip()
        except Exception as e:
            log.exception("Error describiendo imagen: %s", e)
            return ""

def get_vision_model() -> GeminiVision:
    return GeminiVision(model_name=VISION_MODEL or "gemini-1.5-flash")

# Utilidades de path
def normpath(p: str | Path) -> Path:
    return Path(str(p)).resolve()
