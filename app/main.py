import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from app.routers import chat, documents
from app.utils import persistence
from app.utils.excel_handler import create_db_from_excel
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

load_dotenv(override=True)
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@asynccontextmanager
async def lifespan(app: FastAPI):
    excel_path = "data/Seguimiento-hallazgos-Solman.xlsx"
    db_info = await create_db_from_excel(excel_path)
    
    if db_info:
        app.state.db_connection = db_info[0]
        app.state.enriched_schema = db_info[1]
        app.state.sql_keywords = db_info[2]
    else:
        app.state.db_connection = None
        app.state.enriched_schema = ""
        app.state.sql_keywords = []

    async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
        print("✅ DEBUG: Checkpointer conectado y listo.")
        persistence.checkpointer = checkpointer
        yield

    print("❌ DEBUG: Checkpointer cerrado.")
    if hasattr(app.state, 'db_connection') and app.state.db_connection:
        app.state.db_connection.close()
        print("❌ DEBUG: Conexión a la base de datos de Excel cerrada.")

app = FastAPI(
    title="RAG Agent Assistant API",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(chat.router)
app.include_router(documents.router)

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "API is running. Visit /docs for documentation."}