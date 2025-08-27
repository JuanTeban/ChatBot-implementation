import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Corrige la ruta raíz para que apunte a la carpeta principal del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_STORE_PATH = PROJECT_ROOT / "data_store"

UPLOADS_DIR = DATA_STORE_PATH / "uploads"
DUCKDB_DATA_DIR = DATA_STORE_PATH / "duckdb_data"
KNOWLEDGE_BASE_DIR = DATA_STORE_PATH / "knowledge_base"
VECTOR_STORE_DIR = DATA_STORE_PATH / "vector_store"
LOGS_DIR = DATA_STORE_PATH / "logs"
CHARTS_DIR = DATA_STORE_PATH / "charts"

DUCKDB_PATH = DUCKDB_DATA_DIR / "analytics.duckdb"
DUCKDB_LOG_TABLE = "_ingestion_log"

# === CONFIGURACIÓN MULTI-COLECCIÓN ===
CHROMA_COLLECTIONS = {
    "schema_knowledge": "schema_knowledge",      
    "business_rules": "business_rules",          
    "external_docs": "external_docs",
    "multimodal_evidence": "multimodal_evidence",           
}

CHROMA_COLLECTION_NAME = CHROMA_COLLECTIONS["schema_knowledge"]

EMBEDDING_MODEL_NAME = "models/embedding-001"
VECTORIZATION_LOG_FILE = LOGS_DIR / "vectorization_log.json"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")

PDF_STORAGE_PATH = DATA_STORE_PATH / "pdf_reports"
TEMPLATES_PATH = PROJECT_ROOT / "templates"

# === CONFIGURACIONES PARA WEB SCRAPING ===
WEB_SCRAPING_DIR = DATA_STORE_PATH / "web_scraping"
DOCS_STAGING_DIR = WEB_SCRAPING_DIR / "staging"
DOCS_RAW_DIR = DOCS_STAGING_DIR / "raw"
DOCS_TEXT_DIR = DOCS_STAGING_DIR / "text"
DOCS_PROCESSED_DIR = WEB_SCRAPING_DIR / "processed"
SCRAPING_LOGS_DIR = LOGS_DIR / "scraping"

# Configuración específica de scraping
SCRAPING_CONFIG = {
    "sources": [
        {
            "name": "practice_test_automation",
            "base_url": "https://practicetestautomation.com",
            "urls": [
                "https://practicetestautomation.com/practice-test-login/",
            ],
            "domain": "practicetestautomation.com",
            "classification": "external_docs",  # Todo va a external_docs
            "enabled": True
        }
    ],
    "browser": {
        "headless": True,
        "wait_time": 10,
        "page_load_timeout": 30,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    },
    "extraction": {
        "min_content_length": 100,
        "max_content_length": 50000,
        "extract_title": True,
        "extract_metadata": True,
        "clean_html": True
    },
    "dedupe": {
        "enabled": True,
        "hash_algorithm": "sha256"
    }
}

# Configuración de retrieval por dominio
RETRIEVAL_CONFIG = {
    "sql_k": 3,                    
    "business_k": 5,               
    "docs_k": 3,                   
    "similarity_threshold": 0.7,
    "max_chunks_per_collection": 8
}

# === CONFIGURACIÓN MULTIMODAL ===
ENABLE_MULTIMODAL = True
DOCSTORE_PATH = DATA_STORE_PATH / "docstore"
MULTIMODAL_COLLECTION = CHROMA_COLLECTIONS["multimodal_evidence"]  # <-- usar la nueva
VISION_MODEL = "gemini-1.5-flash"

MULTIMODAL_INPUT_ROOT = os.getenv("MULTIMODAL_INPUT_ROOT")

# === CONFIGURACIÓN DE RATE LIMITING ===
ENABLE_RATE_LIMITING = True  # Master switch para control de velocidad
MAX_CONCURRENT_LLM_CALLS = 2  # Máximo 2 llamadas simultáneas
LLM_REQUEST_DELAY = 1.0  # 1 segundo entre requests
CEREBRAS_RETRY_ATTEMPTS = 3  # Máximo 3 reintentos
CEREBRAS_RETRY_DELAY = 2.0  # 2 segundos base para retry

def ensure_data_directories_exist():
    """Crea todos los directorios necesarios si no existen."""
    print("Asegurando la existencia de los directorios de datos...")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DUCKDB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    PDF_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    
    # Directorios para web scraping
    WEB_SCRAPING_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    SCRAPING_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Directorios para multimodal
    DOCSTORE_PATH.mkdir(parents=True, exist_ok=True)
    (DOCSTORE_PATH / "texts").mkdir(exist_ok=True)
    (DOCSTORE_PATH / "tables").mkdir(exist_ok=True) 
    (DOCSTORE_PATH / "images").mkdir(exist_ok=True)
    
    print(f"  - Directorios creados/verificados en: {DATA_STORE_PATH}")

ensure_data_directories_exist()
