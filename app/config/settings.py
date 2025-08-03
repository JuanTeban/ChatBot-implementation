import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_STORE_PATH = PROJECT_ROOT / "data_store"


UPLOADS_DIR = DATA_STORE_PATH / "uploads"
DUCKDB_DATA_DIR = DATA_STORE_PATH / "duckdb_data"
KNOWLEDGE_BASE_DIR = DATA_STORE_PATH / "knowledge_base"
VECTOR_STORE_DIR = DATA_STORE_PATH / "vector_store"
LOGS_DIR = DATA_STORE_PATH / "logs"

DUCKDB_PATH = DUCKDB_DATA_DIR / "analytics.duckdb"
DUCKDB_LOG_TABLE = "_ingestion_log"


CHROMA_COLLECTION_NAME = "sql_knowledge_base"
EMBEDDING_MODEL_NAME = "models/embedding-001"
VECTORIZATION_LOG_FILE = LOGS_DIR / "vectorization_log.json"


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")

def ensure_data_directories_exist():
    """Crea todos los directorios necesarios si no existen."""
    print("Asegurando la existencia de los directorios de datos...")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DUCKDB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  - Directorios creados/verificados en: {DATA_STORE_PATH}")


ensure_data_directories_exist()