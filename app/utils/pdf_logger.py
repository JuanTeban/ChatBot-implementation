import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import json

class PDFLogger:
    """Logger especializado para tracking de generación de PDFs y envío de emails"""
    
    def __init__(self):
        # Configurar logger principal
        self.logger = logging.getLogger("pdf_generation")
        self.logger.setLevel(logging.INFO)
        
        # Crear directorio de logs si no existe
        log_dir = Path("data_store/logs/pdf_flow")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Handler con rotación para logs de PDF
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(
            log_dir / f"pdf_generation_{datetime.now().strftime('%Y%m%d')}.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'  # Forzar encoding UTF-8 para Windows
        )
        
        # Formato detallado con timestamps
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        # Evitar duplicar handlers
        if not self.logger.handlers:
            self.logger.addHandler(handler)
        
        # Métricas de tiempo
        self.timers: Dict[str, float] = {}
        self.metrics: Dict[str, Any] = {}
    
    def start_timer(self, operation: str) -> None:
        """Inicia el timer para una operación"""
        self.timers[operation] = time.time()
        self.logger.info(f"⏱️ INICIO: {operation}")
    
    def end_timer(self, operation: str, success: bool = True) -> float:
        """Finaliza el timer y registra la duración"""
        if operation not in self.timers:
            self.logger.warning(f"⚠️ Timer no encontrado para: {operation}")
            return 0.0
        
        duration = time.time() - self.timers[operation]
        status = "✅" if success else "❌"
        self.logger.info(f"{status} FIN: {operation} - Duración: {duration:.2f}s")
        
        # Guardar métrica
        self.metrics[operation] = {
            "duration": duration,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        
        del self.timers[operation]
        return duration
    
    def log_pdf_generation_start(self, preview_id: str, consultant_name: str) -> None:
        """Log del inicio de generación de PDF"""
        self.logger.info("=" * 80)
        self.logger.info("🚀 INICIANDO GENERACIÓN DE PDF")
        self.logger.info(f"📋 Preview ID: {preview_id}")
        self.logger.info(f"📋 Consultor: {consultant_name}")
        self.logger.info(f"📋 Timestamp: {datetime.now().isoformat()}")
        self.logger.info("=" * 80)
        
        self.start_timer("pdf_generation_total")
    
    def log_pdf_generation_step(self, step: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Log de un paso específico en la generación"""
        details_str = f" - {json.dumps(details)}" if details else ""
        self.logger.info(f"📝 {step}{details_str}")
        self.start_timer(f"step_{step}")
    
    def log_pdf_generation_step_complete(self, step: str, success: bool = True) -> float:
        """Log de completación de un paso"""
        return self.end_timer(f"step_{step}", success)
    
    def log_email_sending_start(self, recipient: str, pdf_path: str) -> None:
        """Log del inicio de envío de email"""
        self.logger.info("📧 INICIANDO ENVÍO DE EMAIL")
        self.logger.info(f"📧 Destinatario: {recipient}")
        self.logger.info(f"📧 PDF: {pdf_path}")
        self.start_timer("email_sending_total")
    
    def log_email_step(self, step: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Log de un paso específico en el envío de email"""
        details_str = f" - {json.dumps(details)}" if details else ""
        self.logger.info(f"📧 {step}{details_str}")
        self.start_timer(f"email_step_{step}")
    
    def log_email_step_complete(self, step: str, success: bool = True) -> float:
        """Log de completación de un paso de email"""
        return self.end_timer(f"email_step_{step}", success)
    
    def log_pdf_generation_complete(self, success: bool = True) -> float:
        """Log de completación de generación de PDF"""
        total_duration = self.end_timer("pdf_generation_total", success)
        
        if success:
            self.logger.info("✅ GENERACIÓN DE PDF COMPLETADA")
        else:
            self.logger.error("❌ GENERACIÓN DE PDF FALLÓ")
        
        self.logger.info(f"⏱️ Tiempo total: {total_duration:.2f}s")
        self.logger.info("=" * 80)
        
        return total_duration
    
    def log_email_complete(self, success: bool = True) -> float:
        """Log de completación de envío de email"""
        total_duration = self.end_timer("email_sending_total", success)
        
        if success:
            self.logger.info("✅ ENVÍO DE EMAIL COMPLETADO")
        else:
            self.logger.error("❌ ENVÍO DE EMAIL FALLÓ")
        
        self.logger.info(f"⏱️ Tiempo total email: {total_duration:.2f}s")
        return total_duration
    
    def log_error(self, operation: str, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """Log de errores con contexto"""
        context_str = f" - Contexto: {json.dumps(context)}" if context else ""
        self.logger.error(f"❌ ERROR en {operation}: {str(error)}{context_str}")
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Obtiene un resumen de las métricas recolectadas"""
        return {
            "total_operations": len(self.metrics),
            "successful_operations": sum(1 for m in self.metrics.values() if m["success"]),
            "failed_operations": sum(1 for m in self.metrics.values() if not m["success"]),
            "average_duration": sum(m["duration"] for m in self.metrics.values()) / len(self.metrics) if self.metrics else 0,
            "operations": self.metrics
        }

# Instancia global
pdf_logger = PDFLogger()
