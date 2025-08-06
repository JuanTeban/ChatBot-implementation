import logging
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict
from app.config.settings import PDF_STORAGE_PATH, TEMPLATES_PATH

logger = logging.getLogger(__name__)

async def create_pdf_report(report_context: Dict[str, Any], template_name: str = "daily_report.html") -> Path:
    """
    Genera un reporte en PDF usando un script externo para evitar problemas de event loop en Windows.
    """
    logger.info(f"    ...Iniciando la creación del archivo PDF (subproceso externo) desde la plantilla '{template_name}'.")

    PDF_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    output_filename = f"reporte_diario_{report_context.get('consultant_name', 'consultor').replace(' ', '_')}_{report_context.get('current_date')}.pdf"
    output_path = PDF_STORAGE_PATH / output_filename

    context_json = json.dumps(report_context, ensure_ascii=False)
    template_path = str(TEMPLATES_PATH / template_name)
    output_pdf_path = str(output_path)

    # CORRECCIÓN: Calcula la ruta absoluta al script en la raíz del proyecto
    PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
    script_path = str(PROJECT_ROOT / "scripts" / "generate_pdf_report.py")

    logger.info(f"Usando sys.executable: {sys.executable}")
    logger.info(f"Script path: {script_path}")

    try:
        subprocess.run(
            [
                sys.executable,
                script_path,
                context_json,
                template_path,
                output_pdf_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(f"    ...PDF generado y guardado exitosamente en: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"    ...Error al generar el PDF con el script externo: {e.stderr}", exc_info=True)
        raise