import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
_prompts = {}

def load_prompts():
    global _prompts
    if _prompts:
        return
    try:
        prompts_path = Path(__file__).parent / "prompts.json"
        with open(prompts_path, "r", encoding="utf-8") as f:
            _prompts = json.load(f)
        logger.info("✅ Prompts del Report Generator cargados.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"❌ No se pudieron cargar los prompts: {e}")
        _prompts = {}

def get_prompt(key: str) -> str:
    if not _prompts:
        load_prompts()
    prompt_template = _prompts.get(key)
    if prompt_template is None:
        logger.error(f"PROMPT_ERROR: Clave '{key}' no encontrada en prompts.json.")
        return f"PROMPT_ERROR: Clave '{key}' no encontrada."
    return prompt_template

def build_sql_prompt(question: str, schema_context: str) -> str:
    tpl = get_prompt("sql_generation_for_report_prompt")
    return tpl.format(question=question, context=schema_context)

# Carga en import
load_prompts()
