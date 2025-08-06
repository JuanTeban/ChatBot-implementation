import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles

# --- Importaciones existentes y nuevas ---
from app.routers import chat, documents, admin
from app.utils import persistence
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# --- NUEVO: Importaciones para el sistema de notificaciones ---
from app.routers import notifications
from app.notifications.scheduler import initialize_scheduler, scheduler

# Carga las variables de entorno desde el archivo .env
load_dotenv(override=True)

# Configuración del logging
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación: se ejecuta al iniciar y al terminar.
    """
    # Código existente para el checkpointer de LangGraph
    async with AsyncSqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
        print("✅ DEBUG: Checkpointer conectado y listo.")
        persistence.checkpointer = checkpointer
        
        # --- NUEVO: Inicia nuestro planificador de tareas al arrancar la app ---
        initialize_scheduler()
        
        yield # La aplicación se ejecuta aquí
    
    # --- NUEVO: Detiene el scheduler de forma segura al apagar la app ---
    if scheduler.running:
        scheduler.shutdown()
        print("❌ DEBUG: Scheduler de notificaciones detenido correctamente.")
    
    print("❌ DEBUG: Checkpointer cerrado.")


# Creación de la instancia de FastAPI
app = FastAPI(
    title="RAG Agent Assistant API",
    version="1.0.0",
    lifespan=lifespan
)

# Montaje de archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Inclusión de todos los routers ---
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(admin.router)
app.include_router(notifications.router) # <-- NUEVO: Añade el router de notificaciones

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "API is running. Visit /docs for documentation."}