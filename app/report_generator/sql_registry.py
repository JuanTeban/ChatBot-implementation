import json, os, time, threading
from typing import Dict, Any, Optional

_LOCK = threading.Lock()
_PATH = os.getenv("REPORT_SQL_REGISTRY", "data/report_sql_registry.json")

def _load() -> Dict[str, Any]:
    if not os.path.exists(_PATH):
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        with open(_PATH, "w", encoding="utf-8") as f: f.write("{}")
    with open(_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f) or {}
        except Exception:
            return {}

def _save(obj: Dict[str, Any]) -> None:
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def save_preview(preview_id: str, payload: Dict[str, Any]) -> None:
    with _LOCK:
        db = _load()
        db.setdefault("previews", {})[preview_id] = {
            "ts": time.time(),
            "preview": payload
        }
        _save(db)

def activate_template_from_preview(preview_id: str, author: str = "system") -> Optional[str]:
    """Guarda la plantilla SQL activa (única) desde un preview aprobado."""
    with _LOCK:
        db = _load()
        pv = (db.get("previews") or {}).get(preview_id)
        if not pv: return None
        tpl = (pv["preview"]["sections"]["summary"]["sql_template"])
        rec = {
            "ts": time.time(),
            "author": author,
            "sql_template": tpl,
            "source_preview": preview_id
        }
        db.setdefault("active_template", rec)
        db["active_template"] = rec
        _save(db)
        return "ok"

def get_active_template() -> Optional[str]:
    db = _load()
    rec = db.get("active_template")
    return rec["sql_template"] if rec else None
