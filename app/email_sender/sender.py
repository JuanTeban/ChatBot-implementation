import smtplib
import logging
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from .config import EMAIL_CONFIG, validate_email_config

logger = logging.getLogger(__name__)

class EmailSender:
    """Clase para manejar el envío de correos electrónicos con PDFs adjuntos"""
    
    def __init__(self):
        self.config = EMAIL_CONFIG
        self.smtp_server = self.config["smtp_server"]
        self.smtp_port = self.config["smtp_port"]
        self.smtp_use_tls = self.config["smtp_use_tls"]
        self.sender_email = self.config["sender_email"]
        self.sender_password = self.config["sender_password"]
        self.sender_name = self.config["sender_name"]
        
    def send_report_email(
        self, 
        pdf_path: str, 
        consultant_name: str, 
        report_id: str,
        recipient_email: Optional[str] = None
    ) -> bool:
        """
        Envía un correo con el PDF del reporte adjunto
        
        Args:
            pdf_path: Ruta al archivo PDF
            consultant_name: Nombre del consultor
            report_id: ID del reporte
            recipient_email: Email del destinatario (opcional, usa test_recipient por defecto)
            
        Returns:
            bool: True si el correo se envió exitosamente, False en caso contrario
        """
        start_time = time.time()
        logger.info("=" * 50)
        logger.info("📧 INICIANDO ENVÍO DE EMAIL")
        logger.info(f"📧 PDF: {pdf_path}")
        logger.info(f"📧 Consultor: {consultant_name}")
        logger.info(f"📧 Report ID: {report_id}")
        logger.info("=" * 50)
        
        try:
            # Paso 1: Validar configuración
            logger.info("⏱️ INICIO: validar_configuracion")
            config_start = time.time()
            if not validate_email_config():
                logger.error("❌ Configuración de correo incompleta")
                return False
            config_time = time.time() - config_start
            logger.info(f"✅ FIN: validar_configuracion - Duración: {config_time:.2f}s")
            
            # Paso 2: Verificar que el PDF existe
            logger.info("⏱️ INICIO: verificar_pdf")
            verify_start = time.time()
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                logger.error(f"❌ Archivo PDF no encontrado: {pdf_path}")
                return False
            verify_time = time.time() - verify_start
            logger.info(f"✅ FIN: verificar_pdf - Duración: {verify_time:.2f}s")
            
            # Paso 3: Determinar destinatario
            logger.info("⏱️ INICIO: determinar_destinatario")
            recipient_start = time.time()
            if not recipient_email:
                recipient_email = self.config["test_recipient"]
            recipient_time = time.time() - recipient_start
            logger.info(f"✅ FIN: determinar_destinatario - Duración: {recipient_time:.2f}s")
            logger.info(f"📧 Destinatario: {recipient_email}")
            
            # Paso 4: Crear el mensaje
            logger.info("⏱️ INICIO: crear_mensaje")
            message_start = time.time()
            message = self._create_email_message(
                pdf_path=str(pdf_file),
                consultant_name=consultant_name,
                report_id=report_id,
                recipient_email=recipient_email
            )
            message_time = time.time() - message_start
            logger.info(f"✅ FIN: crear_mensaje - Duración: {message_time:.2f}s")
            
            # Paso 5: Enviar el correo
            logger.info("⏱️ INICIO: enviar_correo")
            send_start = time.time()
            result = self._send_email(message, recipient_email)
            send_time = time.time() - send_start
            logger.info(f"✅ FIN: enviar_correo - Duración: {send_time:.2f}s")
            
            # Resumen final
            total_time = time.time() - start_time
            logger.info("=" * 50)
            if result:
                logger.info("✅ ENVÍO DE EMAIL COMPLETADO")
            else:
                logger.error("❌ ENVÍO DE EMAIL FALLÓ")
            logger.info(f"⏱️ Tiempo total: {total_time:.2f}s")
            logger.info(f"📊 Desglose:")
            logger.info(f"   - Configuración: {config_time:.2f}s")
            logger.info(f"   - Verificación PDF: {verify_time:.2f}s")
            logger.info(f"   - Crear mensaje: {message_time:.2f}s")
            logger.info(f"   - Envío SMTP: {send_time:.2f}s")
            logger.info("=" * 50)
            
            return result
            
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"❌ Error al enviar correo: {e}")
            logger.error(f"⏱️ Tiempo transcurrido: {total_time:.2f}s")
            return False
    
    def _create_email_message(
        self, 
        pdf_path: str, 
        consultant_name: str, 
        report_id: str,
        recipient_email: str
    ) -> MIMEMultipart:
        """Crea el mensaje de correo con el PDF adjunto"""
        
        # Crear mensaje multipart
        message = MIMEMultipart()
        message['From'] = f"{self.sender_name} <{self.sender_email}>"
        message['To'] = recipient_email
        
        # Obtener plantilla y personalizar
        template = self.config["email_template"]
        subject = template["subject"].format(consultant_name=consultant_name)
        body = template["body"].format(
            consultant_name=consultant_name,
            generation_date=datetime.now().strftime("%d/%m/%Y %H:%M"),
            report_id=report_id
        )
        
        message['Subject'] = subject
        
        # Agregar cuerpo del mensaje
        message.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Adjuntar PDF
        self._attach_pdf(message, pdf_path, consultant_name)
        
        return message
    
    def _attach_pdf(self, message: MIMEMultipart, pdf_path: str, consultant_name: str):
        """Adjunta el archivo PDF al mensaje"""
        try:
            with open(pdf_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            # Codificar en base64
            encoders.encode_base64(part)
            
            # Agregar headers
            filename = f"Reporte_{consultant_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            
            message.attach(part)
            logger.info(f"✅ PDF adjunto: {filename}")
            
        except Exception as e:
            logger.error(f"❌ Error al adjuntar PDF: {e}")
            raise
    
    def _send_email(self, message: MIMEMultipart, recipient_email: str) -> bool:
        """Envía el correo electrónico"""
        try:
            # Paso 1: Conectar al servidor SMTP
            logger.info(f"📧 Conectando a {self.smtp_server}:{self.smtp_port}")
            connect_start = time.time()
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            connect_time = time.time() - connect_start
            logger.info(f"✅ Conexión SMTP establecida en {connect_time:.2f}s")
            
            # Paso 2: Configurar TLS si es necesario
            tls_start = time.time()
            if self.smtp_use_tls:
                server.starttls()
                logger.info("🔒 TLS habilitado")
            tls_time = time.time() - tls_start
            logger.info(f"✅ Configuración TLS completada en {tls_time:.2f}s")
            
            # Paso 3: Iniciar sesión
            logger.info(f"🔐 Iniciando sesión con {self.sender_email}")
            login_start = time.time()
            server.login(self.sender_email, self.sender_password)
            login_time = time.time() - login_start
            logger.info(f"✅ Login completado en {login_time:.2f}s")
            
            # Paso 4: Enviar correo
            logger.info("📤 Enviando mensaje...")
            send_start = time.time()
            text = message.as_string()
            server.sendmail(self.sender_email, recipient_email, text)
            send_time = time.time() - send_start
            logger.info(f"✅ Mensaje enviado en {send_time:.2f}s")
            
            # Paso 5: Cerrar conexión
            close_start = time.time()
            server.quit()
            close_time = time.time() - close_start
            logger.info(f"✅ Conexión cerrada en {close_time:.2f}s")
            
            logger.info(f"✅ Correo enviado exitosamente a {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error al enviar correo: {e}")
            return False

# Instancia global para usar en otros módulos
email_sender = EmailSender()





