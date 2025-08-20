from typing import List, Dict, Set

SUMMARY_REQUIRED_COLS = ["estado_de_defecto", "bloqueante_escenarios", "antiguedad_del_defecto_promedio_en_dias"]
RECO_REQUIRED_COLS    = ["defecto", "antiguedad_del_defecto_promedio_en_dias", "estado_de_defecto"]

def _cols_union(rows: List[Dict]) -> Set[str]:
    cols: Set[str] = set()
    for r in rows or []:
        cols.update(r.keys())
    return cols

def ensure_columns(rows: List[Dict], required: List[str]) -> bool:
    if not rows:
        return False
    cols = _cols_union(rows)
    return all(c in cols for c in required)

def normalize_rows(rows: List[Dict]) -> List[Dict]:
    for r in rows:
        fld = "antiguedad_del_defecto_promedio_en_dias"
        if fld in r and isinstance(r[fld], str):
            r[fld] = r[fld].replace(",", ".")
    return rows

def build_datacard() -> str:
    return (
        "- estado_de_defecto: estado del defecto (p.ej. 'Nuevo', 'En tratamiento', 'Cerrado').\n"
        "- bloqueante_escenarios: 'SI' si bloquea escenarios, 'No' si no bloquea.\n"
        "- antiguedad_del_defecto_promedio_en_dias: número (puede venir como texto con coma decimal); mayor = más antiguo.\n"
        "- Reglas: priorizar bloqueantes y estados 'Nuevo'/'En tratamiento'; resaltar mayor antigüedad.\n"
    )
