# app/utils/persistence.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

checkpointer: AsyncSqliteSaver | None = None

def get_checkpointer() -> AsyncSqliteSaver:
    if checkpointer is None:
        raise RuntimeError("El Checkpointer no ha sido inicializado.")
    return checkpointer