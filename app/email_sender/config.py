import os
from pathlib import Path

# Configuración de correo electrónico
EMAIL_CONFIG = {
    # Configuración del servidor SMTP
    "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "587")),
    "smtp_use_tls": os.getenv("SMTP_USE_TLS", "True").lower() == "true",
    
    # Credenciales del remitente
    "sender_email": os.getenv("SENDER_EMAIL", "tu-email@gmail.com"),
    "sender_password": os.getenv("SENDER_PASSWORD", "tu-password"),
    "sender_name": os.getenv("SENDER_NAME", "Sistema de Reportes"),
    
    # Configuración de destinatarios (para pruebas)
    "test_recipient": os.getenv("TEST_RECIPIENT", "jegarciag@ibm.com"),
    
    # Configuración de plantillas
    "email_template": {
        "subject": "Reporte de Defectos - {consultant_name}",
        "body": """
Estimado/a {consultant_name},

Adjunto encontrará el reporte de defectos generado automáticamente por nuestro sistema.

**Detalles del Reporte:**
- Consultor: {consultant_name}
- Fecha de generación: {generation_date}
- ID del reporte: {report_id}

El reporte incluye:
• Síntesis ejecutiva de los hallazgos
• Plan de acción prioritario
• Análisis gráfico detallado

Si tiene alguna pregunta o necesita información adicional, no dude en contactarnos.

Saludos cordiales,
Sistema de Reportes Automatizados
        """.strip()
    }
}

# Función para validar la configuración
def validate_email_config():
    """Valida que la configuración de correo esté completa"""
    required_vars = [
        "SENDER_EMAIL",
        "SENDER_PASSWORD"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️ Variables de entorno faltantes para correo: {', '.join(missing_vars)}")
        print("   Agrega estas variables a tu archivo .env:")
        for var in missing_vars:
            print(f"   {var}=tu_valor")
        return False
    
    return True





