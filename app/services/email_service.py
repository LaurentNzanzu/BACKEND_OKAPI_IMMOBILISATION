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
    @staticmethod
    def send_organisation_admin_credentials(
        to_email: str,
        org_nom: str,
        login_url: str,
        email: str,
        mot_de_passe_temporaire: str,
    ) -> bool:
        """
        Envoie les identifiants de première connexion à l'admin d'une organisation.
        ⚠️ Le mot de passe n'est JAMAIS stocké en base — il est seulement envoyé ici.
        """
        subject = f"Vos identifiants administrateur — {org_nom}"

        body = (
            f"Bonjour,\n\n"
            f"Un compte administrateur a été créé pour votre organisation « {org_nom} » "
            f"sur la plateforme OKAPI.\n\n"
            f"Voici vos identifiants de première connexion :\n"
            f"  • Email         : {email}\n"
            f"  • Mot de passe  : {mot_de_passe_temporaire}\n\n"
            f"⚠️ Ce mot de passe est TEMPORAIRE. Vous devrez le changer "
            f"lors de votre première connexion.\n\n"
            f"Connexion : {login_url}\n\n"
            f"Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"
            f"— L'équipe OKAPI\n"
        )

        if not EmailService.is_configured():
            if settings.ENVIRONMENT != "production":
                logger.info(
                    "SMTP non configuré — identifiants (dev uniquement) pour %s",
                    to_email,
                )
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
            logger.error("Échec envoi email identifiants pour %s", to_email)
            return False
    
    
    @staticmethod
    def send_new_user_credentials(
        to_email: str,
        prenom: str,
        nom: str,
        email: str,
        mot_de_passe_temporaire: str,
        login_url: str,
        org_nom: Optional[str] = None,
    ) -> bool:
        """
        Envoie les identifiants de première connexion à un nouvel utilisateur.
        ⚠️ Le mot de passe n'est JAMAIS stocké en base — il est seulement envoyé ici.
        """
        org_line = f"au sein de l'organisation « {org_nom} »" if org_nom else "sur la plateforme OKAPI"
        subject = "Vos identifiants de connexion — OKAPI"

        body = (
            f"Bonjour {prenom} {nom},\n\n"
            f"Un compte a été créé pour vous {org_line}.\n\n"
            f"Voici vos identifiants de première connexion :\n"
            f"  • Email         : {email}\n"
            f"  • Mot de passe  : {mot_de_passe_temporaire}\n\n"
            f"⚠️ Ce mot de passe est TEMPORAIRE. Vous devrez le changer "
            f"lors de votre première connexion.\n\n"
            f"Connexion : {login_url}\n\n"
            f"Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"
            f"— L'équipe OKAPI\n"
        )

        if not EmailService.is_configured():
            if settings.ENVIRONMENT != "production":
                logger.info(
                    "SMTP non configuré — identifiants (dev uniquement) pour %s",
                    to_email,
                )
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
            logger.error("Échec envoi email identifiants pour %s", to_email)
            return False

