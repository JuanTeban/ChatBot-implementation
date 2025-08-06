import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.notifications.scheduler import scheduler, daily_reports_job

router = APIRouter(prefix="/notifications", tags=["Notifications"])
logger = logging.getLogger(__name__)

class SchedulerStatus(BaseModel):
    is_running: bool
    job_count: int
    next_run_time: Optional[datetime]

@router.get("/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """
    Verifica el estado actual del planificador de tareas (scheduler).
    """
    if not scheduler or not scheduler.running:
        return {"is_running": False, "job_count": 0, "next_run_time": None}
    
    job = scheduler.get_job("daily_report_job")
    next_run = job.next_run_time if job else None
    
    return {
        "is_running": scheduler.running,
        "job_count": len(scheduler.get_jobs()),
        "next_run_time": next_run
    }

@router.post("/run-now", status_code=202)
async def trigger_job_manually(background_tasks: BackgroundTasks):
    """
    Dispara la ejecución del job de envío de reportes de forma manual.
    Se ejecuta en segundo plano para no bloquear la API.
    """
    background_tasks.add_task(daily_reports_job)
    return {"message": "El job de reportes diarios ha sido iniciado en segundo plano."}

@router.post("/pause", status_code=200)
async def pause_scheduler():
    """
    Pausa el planificador. No se ejecutarán más trabajos programados hasta que se reanude.
    """
    if scheduler.running:
        scheduler.pause()
        logger.info("Scheduler pausado por petición de API.")
        return {"status": "Scheduler pausado."}
    return {"status": "Scheduler no estaba en ejecución."}

@router.post("/resume", status_code=200)
async def resume_scheduler():
    """
    Reanuda un planificador que ha sido pausado.
    """
    if scheduler.running:
        scheduler.resume()
        logger.info("Scheduler reanudado por petición de API.")
        return {"status": "Scheduler reanudado."}
    return {"status": "Scheduler no estaba en ejecución."}