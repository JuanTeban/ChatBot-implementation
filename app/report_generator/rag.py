from typing import List, Dict
from app.etl.retrieval_orchestrator import get_orchestrator

def get_schema_context(goal: str) -> str:
    """
    RAG de esquema para guiar NL→SQL.
    ACTUALIZADO: Usa orquestador multi-colección.
    """
    orchestrator = get_orchestrator()
    return orchestrator.retrieve_for_sql(goal)

def get_business_snippets(query: str, k: int = 6, include_external: bool = False) -> List[Dict]:
    """
    RAG de negocio para redactar con reglas/definiciones.
    ACTUALIZADO: Usa orquestador multi-colección con evidence_ids reales.
    """
    orchestrator = get_orchestrator()
    snippets = orchestrator.retrieve_for_business(query, include_external=include_external)
    
    # Limitar según k solicitado
    if len(snippets) > k:
        snippets = snippets[:k]
    
    return snippets

def join_snippets(snips: List[Dict]) -> str:
    """Une snippets en texto plano para prompts."""
    if not snips:
        return "(sin snippets de negocio - usando solo datos)"
    
    texts = []
    for s in snips:
        source_info = f"[Fuente: {s.get('source', 'unknown')}]"
        texts.append(f"{source_info}\n{s['text']}")
    
    return "\n---\n".join(texts)
