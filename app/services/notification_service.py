import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from typing import List, Optional, Union, Dict, Any
from datetime import datetime, timezone
from ..models.notification import Notification, TypeNotificationEnum, notification_user
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..core.config import settings

logger = logging.getLogger(__name__)

CRITICAL_NOTIFICATION_TYPES = {
    TypeNotificationEnum.ALERTE_STOCK,
    TypeNotificationEnum.ALERTE_VNC_ZERO,
    TypeNotificationEnum.STOCK_INSUFFISANT,
    TypeNotificationEnum.ALERTE_FIN_ECHANCE_MAINTENANCE,
}

IMPORTANT_NOTIFICATION_TYPES = {
    TypeNotificationEnum.BESOIN_CREE,
    TypeNotificationEnum.FOURNITURE_EN_ATTENTE,
    TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
    TypeNotificationEnum.RAPPEL_AMORTISSEMENT_MANQUANT,
}


def _default_priorite_for_type(type_notif: TypeNotificationEnum) -> str:
    if type_notif in CRITICAL_NOTIFICATION_TYPES:
        return "critique"
    if type_notif in IMPORTANT_NOTIFICATION_TYPES:
        return "importante"
    return "information"


def _serialize_notification(
    notification: Notification,
    est_lu: bool = False,
    est_archivee: bool = False,
) -> Dict[str, Any]:
    priorite = getattr(notification, "priorite", None) or "information"
    if hasattr(priorite, "value"):
        priorite = priorite.value
    return {
        "id_notification": notification.id_notification,
        "type_notification": notification.type_notification,
        "titre": notification.titre,
        "contenu": notification.contenu,
        "lien_action": notification.lien_action,
        "date_creation": notification.date_creation,
        "priorite": str(priorite).lower(),
        "est_lu": bool(est_lu),
        "est_archivee": bool(est_archivee),
    }


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def envoyer_notification(
        self,
        ids_destinataires: Union[int, List[int]],
        type_notif: TypeNotificationEnum,
        titre: str,
        contenu: str,
        lien: Optional[str] = None,
        priorite: Optional[str] = None,
    ) -> Optional[Notification]:
        if isinstance(ids_destinataires, int):
            ids_destinataires = [ids_destinataires]

        if not ids_destinataires:
            logger.warning("Aucun destinataire pour la notification")
            return None

        resolved_priorite = priorite or _default_priorite_for_type(type_notif)

        notif = Notification(
            type_notification=type_notif,
            titre=titre,
            contenu=contenu,
            lien_action=lien,
            priorite=resolved_priorite,
            date_creation=datetime.now(timezone.utc),
        )
        self.db.add(notif)
        self.db.flush()

        for id_dest in ids_destinataires:
            self.db.execute(
                notification_user.insert().values(
                    id_notification=notif.id_notification,
                    id_utilisateur=id_dest,
                    est_lu=False,
                    date_lecture=None,
                    est_archivee=False,
                )
            )

        self.db.commit()
        self.db.refresh(notif)

        for id_dest in ids_destinataires:
            self._envoyer_email(id_dest, titre, contenu, lien)

        logger.info("Notification '%s' envoyée à %s destinataire(s)", titre, len(ids_destinataires))
        return notif

    def envoyer_notification_par_role(
        self,
        role_nom: str,
        type_notif: TypeNotificationEnum,
        titre: str,
        contenu: str,
        lien: Optional[str] = None,
        priorite: Optional[str] = None,
    ) -> Optional[Notification]:
        users = self.db.query(Utilisateur).join(Role).filter(Role.nom == role_nom.upper()).all()
        if not users:
            logger.warning("Aucun utilisateur trouvé pour le rôle %s", role_nom)
            return None

        ids_destinataires = [user.id for user in users]
        return self.envoyer_notification(ids_destinataires, type_notif, titre, contenu, lien, priorite)

    def _envoyer_email(self, id_destinataire: int, titre: str, contenu: str, lien: Optional[str]):
        if not all([settings.SMTP_USER, settings.SMTP_PASSWORD, settings.MAIL_FROM]):
            logger.debug("SMTP non configuré.")
            return

        try:
            user = self.db.query(Utilisateur).filter(Utilisateur.id == id_destinataire).first()
            if not user or not user.email:
                return

            msg = MIMEMultipart()
            msg["From"] = settings.MAIL_FROM
            msg["To"] = user.email
            msg["Subject"] = f"[OKAPI] {titre}"

            body = f"{contenu}\n\nPour plus de détails, consultez votre tableau de bord."
            if lien:
                body += f"\n🔗 Lien direct: {lien}"

            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
            logger.info("Email envoyé à %s", user.email)
        except Exception as e:
            logger.error("Échec envoi email SMTP: %s", e)

    def get_non_lues_count(self, id_utilisateur: int) -> int:
        result = self.db.execute(
            notification_user.select().where(
                notification_user.c.id_utilisateur == id_utilisateur,
                notification_user.c.est_lu == False,
                notification_user.c.est_archivee == False,
            )
        )
        return len(list(result))

    def _apply_common_filters(self, stmt, est_lu: Optional[bool], priorite: Optional[str], include_archivees: bool):
        if est_lu is not None:
            stmt = stmt.where(notification_user.c.est_lu == est_lu)
        if priorite:
            stmt = stmt.where(Notification.priorite == priorite.lower())
        if not include_archivees:
            stmt = stmt.where(notification_user.c.est_archivee == False)
        return stmt

    def get_notifications_by_user(
        self,
        id_utilisateur: int,
        limit: int = 50,
        *,
        est_lu: Optional[bool] = None,
        priorite: Optional[str] = None,
        include_archivees: bool = False,
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(Notification, notification_user.c.est_lu, notification_user.c.est_archivee)
            .join(
                notification_user,
                and_(
                    notification_user.c.id_notification == Notification.id_notification,
                    notification_user.c.id_utilisateur == id_utilisateur,
                ),
            )
            .order_by(Notification.date_creation.desc())
            .limit(limit)
        )
        stmt = self._apply_common_filters(stmt, est_lu, priorite, include_archivees)
        rows = self.db.execute(stmt).all()
        return [
            _serialize_notification(row[0], est_lu=row[1], est_archivee=row[2])
            for row in rows
        ]

    def get_all_notifications_for_admin(
        self,
        id_utilisateur: int,
        limit: int = 100,
        *,
        est_lu: Optional[bool] = None,
        priorite: Optional[str] = None,
        include_archivees: bool = False,
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(Notification, notification_user.c.est_lu, notification_user.c.est_archivee)
            .outerjoin(
                notification_user,
                and_(
                    notification_user.c.id_notification == Notification.id_notification,
                    notification_user.c.id_utilisateur == id_utilisateur,
                ),
            )
            .order_by(Notification.date_creation.desc())
            .limit(limit)
        )

        if priorite:
            stmt = stmt.where(Notification.priorite == priorite.lower())

        if est_lu is not None:
            stmt = stmt.where(
                notification_user.c.id_utilisateur.isnot(None),
                notification_user.c.est_lu == est_lu,
            )
            if not include_archivees:
                stmt = stmt.where(notification_user.c.est_archivee == False)
        elif not include_archivees:
            stmt = stmt.where(
                (notification_user.c.est_archivee == False)
                | (notification_user.c.id_utilisateur.is_(None))
            )

        rows = self.db.execute(stmt).all()
        return [
            _serialize_notification(
                row[0],
                est_lu=bool(row[1]) if row[1] is not None else False,
                est_archivee=bool(row[2]) if row[2] is not None else False,
            )
            for row in rows
        ]

    def marquer_comme_lue(self, id_notification: int, id_utilisateur: int) -> bool:
        result = self.db.execute(
            notification_user.update()
            .where(
                notification_user.c.id_notification == id_notification,
                notification_user.c.id_utilisateur == id_utilisateur,
            )
            .values(est_lu=True, date_lecture=datetime.now(timezone.utc))
        )
        self.db.commit()
        return result.rowcount > 0

    def marquer_tout_comme_lu(self, id_utilisateur: int) -> int:
        result = self.db.execute(
            notification_user.update()
            .where(
                notification_user.c.id_utilisateur == id_utilisateur,
                notification_user.c.est_lu == False,
                notification_user.c.est_archivee == False,
            )
            .values(est_lu=True, date_lecture=datetime.now(timezone.utc))
        )
        self.db.commit()
        return result.rowcount

    def archiver_notification(self, id_notification: int, id_utilisateur: int) -> bool:
        result = self.db.execute(
            notification_user.update()
            .where(
                notification_user.c.id_notification == id_notification,
                notification_user.c.id_utilisateur == id_utilisateur,
            )
            .values(est_archivee=True)
        )
        self.db.commit()
        if result.rowcount > 0:
            logger.info(
                "Notification archivée | notification_id=%s user_id=%s",
                id_notification,
                id_utilisateur,
            )
            return True
        logger.warning(
            "Archivage refusé | notification_id=%s user_id=%s",
            id_notification,
            id_utilisateur,
        )
        return False

    def get_historique(
        self,
        id_utilisateur: int,
        limit: int = 50,
        *,
        est_lu: Optional[bool] = None,
        priorite: Optional[str] = None,
        include_archivees: bool = False,
    ) -> List[Dict[str, Any]]:
        return self.get_notifications_by_user(
            id_utilisateur,
            limit,
            est_lu=est_lu,
            priorite=priorite,
            include_archivees=include_archivees,
        )
