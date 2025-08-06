import aiosmtplib
from email.message import EmailMessage
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

# Carga la configuración de forma segura desde las variables de entorno
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_NAME = os.getenv("SENDER_NAME", "Asistente IA")

async def send_email_with_attachment(
    recipient_email: str,
    subject: str,
    html_content: str,
    attachment_path: Path,
) -> bool:
    """
    Envía de forma asíncrona un correo electrónico con un archivo adjunto.

    Returns:
        True si el correo se envió con éxito, False en caso de error.
    """
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SENDER_EMAIL]):
        logger.error("Configuración de SMTP incompleta. Revisa las variables de entorno (.env).")
        return False

    logger.info(f"    ...Configurando y conectando al servidor SMTP ({SMTP_HOST}:{SMTP_PORT}).")
    message = EmailMessage()
    message["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    message["To"] = recipient_email
    message["Subject"] = subject
    
    # Establece el contenido principal como HTML
    message.add_alternative(html_content, subtype="html")

    try:
        # Adjunta el archivo PDF
        with open(attachment_path, "rb") as f:
            file_data = f.read()
            message.add_attachment(
                file_data,
                maintype="application",
                subtype="pdf", # Específicamente para PDF
                filename=attachment_path.name,
            )

        # Conecta con el servidor SMTP y envía el correo
        await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
        )
        logger.info(f"    ...Correo enviado exitosamente a {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"    ...Fallo al enviar correo a {recipient_email}: {e}", exc_info=True)
        return False