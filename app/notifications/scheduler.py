import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import duckdb
from pathlib import Path
import asyncio
from datetime import datetime
from typing import List

# --- Bloque de importaciones corregido ---
from app.config.settings import DUCKDB_PATH
from app.models.pydantic_models import Consultant # <-- RUTA CORREGIDA
from app.notifications.llm_analyst import generate_report_content
from app.notifications.pdf_generator import create_pdf_report # <-- Sigue igual la importación
from app.notifications.email_sender import send_email_with_attachment

logger = logging.getLogger(__name__)
TIMEZONE = os.getenv("TIMEZONE", "UTC")
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

def get_all_consultants() -> List[Consultant]:
    """
    Obtiene una lista de todos los consultores únicos y sus correos.
    --- MODO DE PRUEBA ---
    Esta versión solo devuelve el primer consultor encontrado y le asigna
    un correo de prueba estático para la validación.
    """
    # === CORRECCIÓN: Se crea la columna 'email' estáticamente en la consulta ===
    query = """
    SELECT DISTINCT 
        responsable_del_defecto AS name, 
        'kazodroid@gmail.com' AS email
    FROM seguimiento_hallazgos_solman_seguimiento_detalles_defecto
    WHERE name IS NOT NULL
    LIMIT 1; -- Obtenemos solo un consultor para la prueba
    """
    # === NUEVO LOG: Mostramos la consulta exacta que se va a ejecutar ===
    logger.info(f"Ejecutando consulta para obtener consultores:\n{query}")
    
    if not DUCKDB_PATH.exists():
        logger.error(f"¡ERROR CRÍTICO! La base de datos no se encuentra en la ruta esperada: {DUCKDB_PATH}. Por favor, asegúrese de que el proceso ETL (Ingesta de datos) se haya ejecutado correctamente desde el panel de administración.")
        return []

    try:
        con = duckdb.connect(database=str(DUCKDB_PATH), read_only=True)
        consultant_dicts = con.execute(query).fetch_df().to_dict('records')
        
        if not consultant_dicts:
            logger.warning("MODO PRUEBA: No se encontraron consultores en la base de datos para probar.")
            return []

        # Tomamos el primer consultor y modificamos sus datos para la prueba
        test_consultant_data = consultant_dicts[0]
        test_consultant_data['email'] = 'kazodroid@gmail.com'
        
        consultants = [Consultant.model_validate(test_consultant_data)]
        con.close()

        logger.info(f"MODO PRUEBA: Se preparó el reporte para '{consultants[0].name}' y se enviará a '{consultants[0].email}'.")
        return consultants
        
    except Exception as e:
        logger.error(f"Error al obtener la lista de consultores para la prueba: {e}", exc_info=True)
        return []

async def process_and_send_report(consultant: Consultant):
    logger.info(f"-> INICIANDO PIPELINE para {consultant.name} ({consultant.email})")
    
    pdf_path = None
    try:
        logger.info(f"  [Paso 1/4] Invocando agente para generar contenido...")
        report_content = await generate_report_content(consultant.name, str(consultant.email))
        logger.info(f"  ...Contenido recibido del agente.")
        
        pdf_context = {
            "consultant_name": consultant.name,
            "generation_date": datetime.now().strftime("%d de %B de %Y"),
            "summary": report_content.get("summary", "Resumen no disponible."),
            "recommendations": report_content.get("recommendations", "Recomendaciones no disponibles."),
            "chart_spec": report_content.get("chart_spec"),
            "current_date": datetime.now().strftime("%Y-%m-%d"),
        }
        
        logger.info("  [Paso 2/4] Generando PDF...")
        pdf_path = await create_pdf_report(pdf_context)

        subject = f"Reporte Diario de Hallazgos - {consultant.name}"
        html_body = f"<h3>Hola {consultant.name},</h3><p>Adjunto encontrarás tu reporte diario personalizado.</p><p>Saludos,<br>Asistente Tabalux</p>"
        
        logger.info(f"  [Paso 3/4] Preparando para enviar correo a {consultant.email}...")
        success = await send_email_with_attachment(
            recipient_email=str(consultant.email),
            subject=subject,
            html_content=html_body,
            attachment_path=pdf_path
        )

        logger.info(f"  [Paso 4/4] Finalizando y limpiando...")
        if success and pdf_path and pdf_path.exists():
            logger.info(f"    ...Correo enviado. Eliminando PDF: {pdf_path}")
            pdf_path.unlink()
        elif not success:
            logger.warning(f"    ...El envío de correo falló. El PDF se conservará para revisión: {pdf_path}")
        else:
            logger.info(f"    ...No hay PDF para limpiar o ya fue eliminado.")

    except Exception as e:
        logger.error(f"-> ERROR CRÍTICO en pipeline para {consultant.name}: {e}", exc_info=True)
        if pdf_path and pdf_path.exists():
             logger.info(f"  ...Limpiando PDF temporal ({pdf_path}) debido al error.")
             pdf_path.unlink()
    
    logger.info(f"-> PIPELINE FINALIZADO para {consultant.name}.")

async def daily_reports_job():
    """
    Tarea principal que se ejecuta diariamente.
    """
    # === NUEVO LOG DE DEPURACIÓN: Verificar la política del event loop ===
    try:
        current_policy = asyncio.get_event_loop_policy().__class__.__name__
        logger.info(f"--- DEBUG: La política del event loop DENTRO DEL JOB es: {current_policy} ---")
    except Exception as e:
        logger.error(f"--- DEBUG: No se pudo obtener la política del event loop: {e} ---")
        
    logger.info(f"--- INICIANDO JOB DE REPORTES DIARIOS ({datetime.now()}) ---")
    
    # === NUEVO LOG: Listamos todas las tablas disponibles para facilitar la depuración ===
    try:
        con = duckdb.connect(database=str(DUCKDB_PATH), read_only=True)
        tables = con.execute("SHOW TABLES;").fetchdf()
        logger.info(f"Tablas disponibles en DuckDB:\n{tables}")
        con.close()
    except Exception as e:
        logger.error(f"No se pudieron listar las tablas de DuckDB: {e}")
    
    consultants = get_all_consultants()
    if not consultants:
        logger.warning("No hay consultores para procesar. Finalizando job.")
        return

    tasks = [process_and_send_report(c) for c in consultants]
    await asyncio.gather(*tasks)
    
    logger.info(f"--- JOB DE REPORTES DIARIOS FINALIZADO ({datetime.now()}) ---")

def initialize_scheduler():
    cron_expression = os.getenv("MAIL_SCHEDULE_CRON", "0 7 * * *")
    try:
        scheduler.add_job(
            daily_reports_job,
            CronTrigger.from_crontab(cron_expression, timezone=TIMEZONE),
            id="daily_report_job",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(f"Scheduler iniciado. Tarea programada con la expresión: '{cron_expression}' en zona horaria {TIMEZONE}.")
    except Exception as e:
        logger.error(f"No se pudo iniciar el scheduler: {e}", exc_info=True)