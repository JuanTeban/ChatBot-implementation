import os
from dotenv import load_dotenv

load_dotenv()

DEBUGGER_ADDRESS = os.getenv("DEBUGGER_ADDRESS")
DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER")
# Nueva línea para el modo debug
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() in ('true', '1', 't')