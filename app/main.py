import logging
from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from app.routers import chat, documents

load_dotenv(override=True)

logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI(
    title="RAG Agent Assistant API",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(chat.router)
app.include_router(documents.router)

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "API is running. Visit /docs for documentation."}