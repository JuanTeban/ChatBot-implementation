import json
import logging
import re
from typing import Dict, Any, List
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.io as pio

from app.agent.shared import answer_llm
from .prompts import get_prompt
from app.utils.rate_limiter import with_rate_limiting

log = logging.getLogger(__name__)

COL_DEFECTO = "defecto"
COL_COMENT = "comentarios"
COL_AGE = "antiguedad_del_defecto_promedio_en_dias"
_DATE_RE = re.compile(r"(?:^|[^0-9])(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?:[^0-9]|$)")

def _to_float_locale(x):
    if x is None: return None
    if isinstance(x, (int, float)): return float(x)
    s = str(x).strip().replace('\xa0', '').replace(' ', '')
    if s == '' or s.lower() == 'nan': return None
    if ',' in s:
        if '.' in s: s = s.replace('.', '')
        s = s.replace(',', '.')
    return float(s)

def _parse_dates_from_text(s: str):
    if not isinstance(s, str) or not s.strip(): return []
    out = []
    for m in _DATE_RE.findall(s.replace("\n", " ")):
        d = m.replace("-", "/")
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                out.append(datetime.strptime(d, fmt).replace(tzinfo=timezone.utc))
                break
            except ValueError: continue
    return out

def _fig_to_jsonsafe_spec(fig):
    return json.loads(pio.to_json(fig, validate=False))

def _is_valid_plotly_spec(obj: Dict[str, Any]) -> bool:
    if not isinstance(obj, dict): return False
    if "data" not in obj or "layout" not in obj: return False
    try:
        json.dumps(obj)
        return True
    except Exception:
        return False

@with_rate_limiting
async def build_llm_chart(data: List[Dict], goal: str) -> Dict[str, Any]:
    log.info(f"Iniciando gráfico LLM (datos brutos). Objetivo: '{goal}'. Filas: {len(data)}.")
    if not data:
        log.warning("No hay datos para generar el gráfico por LLM, se devuelve un spec vacío.")
        return {}
    try:
        prompt_tpl = get_prompt("chart_generation_from_data_prompt")
        prompt = prompt_tpl.format(goal=goal, data_json=json.dumps(data, ensure_ascii=False))
        resp = await answer_llm.ainvoke(prompt)
        chart_spec_str = resp.content.strip().replace("```json", "").replace("```", "")
        spec = json.loads(chart_spec_str)
        if _is_valid_plotly_spec(spec):
            return spec
    except Exception as e:
        log.error(f"No se pudo generar el gráfico para el objetivo '{goal}': {e}", exc_info=True)

    # Fallback simple (barras por defecto si hay 'defecto' y 'antiguedad')
    try:
        df = pd.DataFrame(data)
        if COL_DEFECTO in df and COL_AGE in df:
            fig = px.bar(df.sort_values(COL_AGE, ascending=False), x=COL_DEFECTO, y=COL_AGE,
                         title="Antigüedad de cada defecto (fallback)")
            fig.update_xaxes(tickangle=-45)
            return _fig_to_jsonsafe_spec(fig)
    except Exception:
        pass
    return {}

async def build_aggregated_llm_chart(df: pd.DataFrame, group_by_col: str, agg_col: str, goal: str) -> Dict[str, Any]:
    log.info(f"Iniciando gráfico LLM (datos agregados). Objetivo: '{goal}'. Agrupando por '{group_by_col}'.")
    if df.empty or group_by_col not in df.columns:
        log.warning(f"DataFrame vacío o columna '{group_by_col}' no encontrada.")
        return {}
    agg_df = df.groupby(group_by_col, as_index=False).agg(count=(agg_col, 'count'))
    agg_df.rename(columns={'count': f'cantidad_de_{agg_col}'}, inplace=True)
    aggregated_data = agg_df.to_dict(orient='records')
    return await build_llm_chart(aggregated_data, goal)

def build_inactivity_risk_chart(df: pd.DataFrame) -> Dict[str, Any]:
    log.info(f"Construyendo gráfico de inactividad. DataFrame de entrada: {df.shape[0]} filas.")
    if df.empty or COL_COMENT not in df or COL_AGE not in df: return {}
    today = datetime.now(timezone.utc)
    rows = []
    for _, r in df.iterrows():
        age = _to_float_locale(r.get(COL_AGE))
        dates = _parse_dates_from_text(str(r.get(COL_COMENT, "")))
        last = max(dates) if dates else None
        last_days = (today - last).days if last else None
        label = str(r.get(COL_DEFECTO, ""))
        rows.append({"Antigüedad Total": age, "Días desde Última Actividad": last_days, "Defecto": label})
    plot_df = pd.DataFrame(rows).dropna(subset=["Antigüedad Total", "Días desde Última Actividad"])
    if plot_df.empty: return {}
    fig = px.scatter(plot_df, x="Antigüedad Total", y="Días desde Última Actividad", hover_name="Defecto",
                     title="Relación Antigüedad vs. Última Actividad")
    return _fig_to_jsonsafe_spec(fig)

def build_effort_iterations_chart(df: pd.DataFrame) -> Dict[str, Any]:
    log.info(f"Construyendo gráfico de esfuerzo. DataFrame de entrada: {df.shape[0]} filas.")
    if df.empty or COL_COMENT not in df: return {}
    rows = []
    for _, r in df.iterrows():
        defect = str(r.get(COL_DEFECTO, ""))
        n_dates = len(_parse_dates_from_text(str(r.get(COL_COMENT, ""))))
        rows.append({"Defecto": defect, "Iteraciones": n_dates})
    plot_df = (pd.DataFrame(rows)
               .groupby("Defecto", as_index=False)["Iteraciones"].sum()
               .sort_values("Iteraciones", ascending=False))
    if plot_df.empty: return {}
    fig = px.bar(plot_df, x="Defecto", y="Iteraciones", title="Número de Iteraciones por Defecto")
    fig.update_xaxes(tickangle=-45)
    return _fig_to_jsonsafe_spec(fig)
