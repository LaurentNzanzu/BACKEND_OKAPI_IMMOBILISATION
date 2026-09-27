import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from typing import Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.SMTP_USER and settings.SMTP_PASSWORD and settings.MAIL_FROM)

    @staticmethod
    def send_password_reset_email(to_email: str, reset_link: str) -> bool:
        subject = "Réinitialisation de votre mot de passe"
        body = (
            "Bonjour,\n\n"
            "Vous avez demandé la réinitialisation de votre mot de passe.\n"
            f"Cliquez sur le lien suivant (valide 5 minutes) :\n{reset_link}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"
        )

        if not EmailService.is_configured():
            if settings.ENVIRONMENT != "production":
                logger.info("SMTP non configuré — lien reset (dev uniquement) pour %s", to_email)
            return False

        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = settings.MAIL_FROM
            msg["To"] = to_email

            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=10) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.MAIL_FROM, [to_email], msg.as_string())
            return True
        except Exception:
            # Une exception SMTP peut contenir le message et donc le lien secret.
            logger.error("Échec envoi email reset")
            return False
