import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles

from app.routers import chat, documents
from app.utils import persistence
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

load_dotenv(override=True)

logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
        print("✅ DEBUG: Checkpointer conectado y listo.")
        persistence.checkpointer = checkpointer
        yield
    print("❌ DEBUG: Checkpointer cerrado.")


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