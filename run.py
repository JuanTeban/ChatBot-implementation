import os
import sys
import asyncio
from dotenv import load_dotenv
import uvicorn

# Cargar variables de entorno
load_dotenv()

# En Windows, usar ProactorEventLoop para que asyncio soporte subprocesos
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_excludes=["scripts/*"],  # con --reload Uvicorn también respeta la política que hemos fijado
    )
