#!/usr/bin/env python3
"""
Script para probar el sistema de logging de PDFs
Simula el flujo completo de generación y envío para verificar que los logs funcionan correctamente
"""

import asyncio
import time
import sys
from pathlib import Path

# Agregar el directorio raíz al path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.pdf_logger import pdf_logger
from app.email_sender.sender import email_sender

async def test_pdf_logging():
    """Prueba el sistema de logging de PDFs"""
    
    print("🧪 INICIANDO PRUEBA DEL SISTEMA DE LOGGING DE PDFS")
    print("=" * 60)
    
    # Simular datos de prueba
    preview_id = "test_preview_123"
    consultant_name = "Consultor de Prueba"
    
    try:
        # 1. Probar logging de inicio de generación de PDF
        print("📝 Probando logging de inicio de generación...")
        pdf_logger.log_pdf_generation_start(preview_id, consultant_name)
        
        # 2. Simular pasos de generación
        steps = [
            "preparar_url_y_directorio",
            "generar_pdf_subproceso", 
            "verificar_pdf"
        ]
        
        for step in steps:
            print(f"📝 Probando paso: {step}")
            pdf_logger.log_pdf_generation_step(step, {"test": True})
            
            # Simular tiempo de procesamiento
            await asyncio.sleep(0.5)
            
            pdf_logger.log_pdf_generation_step_complete(step, True)
        
        # 3. Completar generación de PDF
        print("📝 Completando generación de PDF...")
        total_time = pdf_logger.log_pdf_generation_complete(True)
        print(f"✅ Tiempo total de generación: {total_time:.2f}s")
        
        # 4. Probar logging de email
        print("📧 Probando logging de email...")
        pdf_logger.log_email_sending_start("test@example.com", "/path/to/test.pdf")
        
        email_steps = [
            "validar_configuracion",
            "verificar_pdf",
            "crear_mensaje"
        ]
        
        for step in email_steps:
            print(f"📧 Probando paso de email: {step}")
            pdf_logger.log_email_step(step, {"test": True})
            
            # Simular tiempo de procesamiento
            await asyncio.sleep(0.3)
            
            pdf_logger.log_email_step_complete(step, True)
        
        # 5. Completar envío de email
        print("📧 Completando envío de email...")
        email_time = pdf_logger.log_email_complete(True)
        print(f"✅ Tiempo total de email: {email_time:.2f}s")
        
        # 6. Probar logging de errores
        print("❌ Probando logging de errores...")
        test_error = Exception("Error de prueba para verificar logging")
        pdf_logger.log_error("test_operation", test_error, {"test_context": True})
        
        # 7. Obtener métricas
        print("📊 Obteniendo métricas...")
        metrics = pdf_logger.get_metrics_summary()
        print(f"📊 Total de operaciones: {metrics['total_operations']}")
        print(f"📊 Operaciones exitosas: {metrics['successful_operations']}")
        print(f"📊 Operaciones fallidas: {metrics['failed_operations']}")
        print(f"📊 Tiempo promedio: {metrics['average_duration']:.2f}s")
        
        print("\n✅ PRUEBA COMPLETADA EXITOSAMENTE")
        print("📁 Los logs se han guardado en: data_store/logs/pdf_flow/")
        
    except Exception as e:
        print(f"❌ Error durante la prueba: {e}")
        pdf_logger.log_error("test_pdf_logging", e, {"test": True})

async def test_email_sender_logging():
    """Prueba el logging del email sender"""
    
    print("\n🧪 INICIANDO PRUEBA DEL LOGGING DE EMAIL SENDER")
    print("=" * 60)
    
    try:
        # Crear un archivo PDF de prueba
        test_pdf_path = Path("exports/test_pdf.pdf")
        test_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Crear un PDF vacío para la prueba
        with open(test_pdf_path, 'w') as f:
            f.write("Test PDF content")
        
        print(f"📄 Archivo PDF de prueba creado: {test_pdf_path}")
        
        # Probar envío de email (esto activará el logging detallado)
        print("📧 Probando envío de email con logging...")
        
        # Nota: Esto puede fallar si no hay configuración de email válida
        # pero el logging debería funcionar de todas formas
        try:
            result = email_sender.send_report_email(
                pdf_path=str(test_pdf_path),
                consultant_name="Consultor de Prueba",
                report_id="test_report_123"
            )
            print(f"📧 Resultado del envío: {result}")
        except Exception as e:
            print(f"⚠️  El envío falló (esperado si no hay configuración): {e}")
            print("✅ Pero el logging debería haber funcionado correctamente")
        
        # Limpiar archivo de prueba
        if test_pdf_path.exists():
            test_pdf_path.unlink()
            print("🧹 Archivo de prueba eliminado")
        
    except Exception as e:
        print(f"❌ Error durante la prueba de email: {e}")

def main():
    """Función principal"""
    print("🚀 SISTEMA DE LOGGING DE PDFS - PRUEBAS")
    print("=" * 60)
    
    # Ejecutar pruebas
    asyncio.run(test_pdf_logging())
    asyncio.run(test_email_sender_logging())
    
    print("\n" + "=" * 60)
    print("📋 RESUMEN DE PRUEBAS")
    print("=" * 60)
    print("✅ Sistema de logging de PDFs probado")
    print("✅ Sistema de logging de emails probado")
    print("📁 Verifica los archivos de log en: data_store/logs/pdf_flow/")
    print("🔍 Usa el script analyze_pdf_performance.py para analizar los logs")

if __name__ == "__main__":
    main()
