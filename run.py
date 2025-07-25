import os
from dotenv import load_dotenv
import uvicorn

# Cargar variables de entorno desde .env
load_dotenv()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 