import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_prompts = {}

def load_prompts():
    """Carga los prompts desde el archivo prompts.json."""
    global _prompts
    if _prompts:
        return

    try:
        prompts_path = Path(__file__).parent / "prompts.json"
        with open(prompts_path, "r", encoding="utf-8") as f:
            _prompts = json.load(f)
        logger.info("✅ Prompts cargados exitosamente desde prompts.json")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"❌ No se pudieron cargar los prompts desde prompts.json: {e}")
        # En caso de error, usamos un diccionario vacío para evitar que la app se caiga.
        _prompts = {}

def get_prompt(key: str) -> str:
    """
    Obtiene un prompt por su clave.

    Args:
        key: La clave del prompt a obtener (e.g., 'router_system_prompt').

    Returns:
        El texto del prompt o un mensaje de error si no se encuentra.
    """
    if not _prompts:
        load_prompts()
    
    prompt_template = _prompts.get(key)
    if prompt_template is None:
        logger.error(f"PROMPT_ERROR: Clave de prompt '{key}' no encontrada en prompts.json.")
        return f"PROMPT_ERROR: Clave '{key}' no encontrada."
    return prompt_template


load_prompts() 