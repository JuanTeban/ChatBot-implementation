# scripts/export_pdfs.py
import asyncio
import os
import json
import urllib.parse
from pathlib import Path
import sys  # <-- ESTA ES LA LÍNEA QUE FALTABA

# Añadir la ruta del proyecto al sys.path para poder importar 'app'
# Esto es crucial para que el script pueda encontrar 'app.tools.tools'
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from pyppeteer import launch  # pip install pyppeteer
from app.tools.tools import execute_duckdb_query

BASE_URL = os.getenv("REPORTS_BASE_URL", "http://127.0.0.1:8000")  # donde corre FastAPI
OUTPUT   = Path(os.getenv("REPORTS_OUT", "./exports")).resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)

def _duck_to_rows(raw: str):
    obj = json.loads(raw or "{}"); 
    if "SQL_ERROR" in (obj.get("table_str") or ""): 
        raise RuntimeError(obj.get("table_str"))
    return obj.get("json_data") or []

def get_responsables(limit: int = 4):
    sql = """
    SELECT DISTINCT responsable_del_defecto AS responsable
    FROM seguimiento_hallazgos_solman_seguimiento_detalles_defecto
    WHERE responsable_del_defecto IS NOT NULL
      AND LENGTH(TRIM(responsable_del_defecto)) > 0
    ORDER BY 1 LIMIT {limit};
    """.format(limit=limit)
    rows = _duck_to_rows(execute_duckdb_query.invoke({"sql_query": sql}))
    responsables = [r["responsable"] for r in rows if r.get("responsable")]
    print(f"Responsables encontrados: {responsables}")
    return responsables

async def export_one(responsable: str):
    """Genera un PDF para un responsable usando la plantilla activa."""
    # --- INICIO DEL CAMBIO ---
    # La URL ahora apunta a la nueva ruta que usa la plantilla activa,
    # haciendo el script independiente de cualquier preview_id.
    url = f"{BASE_URL}/reports/render_active?responsable=" + urllib.parse.quote(responsable)
    # --- FIN DEL CAMBIO ---
    
    out_pdf = OUTPUT / f"Reporte_{responsable.replace(' ', '_').replace('(', '').replace(')', '')}.pdf"
    
    print(f"  -> Exportando reporte para '{responsable}' desde {url}...")
    
    # --- INICIO DE LA CORRECCIÓN ---
    # Especificamos la ruta a un navegador Chromium existente (Chrome o Edge)
    # para evitar el problema de la descarga automática.
    browser_executable_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    if not Path(browser_executable_path).exists():
        # Si no tienes Chrome, prueba con Edge
        browser_executable_path = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"

    if not Path(browser_executable_path).exists():
        raise FileNotFoundError(
            "No se encontró Google Chrome ni Microsoft Edge en las rutas estándar. "
            "Asegúrate de tener uno de ellos instalado o ajusta la ruta en el script."
        )

    browser = await launch(
        executablePath=browser_executable_path,
        args=["--no-sandbox", "--disable-gpu"]
    )
    # --- FIN DE LA CORRECCIÓN ---

    page = await browser.newPage()
    try:
        await page.goto(url, {"waitUntil": "networkidle2", "timeout": 60000})
        # espera corta para que Plotly termine
        await asyncio.sleep(2.0)
        await page.pdf({
            "path": str(out_pdf),
            "format": "A4",
            "printBackground": True,
            "margin": {"top":"12mm","right":"12mm","bottom":"12mm","left":"12mm"}
        })
        print(f"✔ Guardado {out_pdf}")
    except Exception as e:
        print(f"Error al exportar el reporte para {responsable}: {e}")
    finally:
        await browser.close()

async def main(n: int = 4):
    print("--- Iniciando exportación masiva usando la plantilla activa ---")
    
    responsables = get_responsables(limit=n)
    print(f"Responsables encontrados: {responsables}")
    
    # 🚨 CAMBIO CRÍTICO: Procesar secuencialmente en lugar de en paralelo
    for responsable in responsables:
        print(f"  -> Exportando reporte para '{responsable}'...")
        try:
            await export_one(responsable)
            # Pausa entre reportes para evitar rate limiting
            await asyncio.sleep(2)  
        except Exception as e:
            print(f"Error al exportar el reporte para {responsable}: {e}")
    
    print("--- Proceso de exportación finalizado. ---")

if __name__ == "__main__":
    # El script ya no necesita el preview_id como argumento
    print("Uso: python -m scripts.export_pdfs [cantidad_de_reportes=4]")
    num_reports = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    
    # Usar asyncio.run() que es la forma moderna y segura de correr el loop
    asyncio.run(main(num_reports))
