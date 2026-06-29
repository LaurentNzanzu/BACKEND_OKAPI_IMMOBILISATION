# backend/app/services/notification_service.py
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

        import asyncio
        for id_dest in ids_destinataires:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.run_in_executor(None, self._envoyer_email, id_dest, titre, contenu, lien)
                else:
                    self._envoyer_email(id_dest, titre, contenu, lien)
            except RuntimeError:
                import threading
                threading.Thread(target=self._envoyer_email, args=(id_dest, titre, contenu, lien)).start()

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
        from ..core.redis import CacheService
        from ..core.database import LocalCache
        from sqlalchemy import text

        cache_key = f"unread_count:{id_utilisateur}"
        cached_count = LocalCache.get(cache_key) or CacheService.get(cache_key)
        if cached_count is not None:
            return int(cached_count)

        count = self.db.execute(
            text("""
                SELECT COUNT(*) 
                FROM notification_user 
                WHERE id_utilisateur = :user_id 
                  AND est_lu = false 
                  AND est_archivee = false
            """),
            {"user_id": id_utilisateur}
        ).scalar() or 0

        LocalCache.set(cache_key, count, ttl_seconds=300)
        CacheService.set(cache_key, count, ttl=300)
        return count

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
        skip: int = 0,
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
            .offset(skip)
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
        skip: int = 0,
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
            .offset(skip)
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

    # ============================================================
    # MÉTHODES TÂCHE 2 - NOTIFICATIONS WORKFLOW
    # ============================================================
    
    def notifier_validation_etape(self, objet_type: str, objet_id: int, 
                                   etape: str, decision: str,
                                   validateur_nom: str, motif: str = None):
        """
        Notifie les parties prenantes d'une étape de validation.
        """
        titre = f"{'✅' if decision == 'APPROUVE' else '❌'} Validation {decision} - {objet_type} #{objet_id}"
        
        if decision == 'APPROUVE':
            contenu = f"La validation de {objet_type} a été approuvée par {validateur_nom} (étape: {etape})"
        else:
            contenu = f"La validation de {objet_type} a été rejetée par {validateur_nom} (étape: {etape}). Motif: {motif or 'Non spécifié'}"
        
        # Notifier le créateur
        # Note: Dans une implémentation réelle, il faudrait récupérer l'ID du créateur
        # pour l'objet concerné. Cette méthode est générique et nécessite que l'appelant
        # fournisse l'ID du créateur ou que la méthode le récupère via l'objet.
        # Pour l'instant, on notifie par rôle "ADMIN" comme fallback
        self.envoyer_notification_par_role(
            role_nom="ADMIN",
            type_notif=TypeNotificationEnum.BESOIN_VALIDE if decision == 'APPROUVE' else TypeNotificationEnum.BESOIN_REJETE,
            titre=titre,
            contenu=contenu,
            lien=f"/{objet_type.lower()}s/{objet_id}"
        )

    def notifier_nouvelle_etape_validation(self, objet_type: str, objet_id: int,
                                            etape: str, prochain_validateur: str):
        """
        Notifie le prochain validateur qu'une nouvelle étape est disponible.
        """
        titre = f"📋 Nouvelle validation requise - {objet_type} #{objet_id}"
        contenu = f"Un {objet_type} est en attente de votre validation ({etape})."
        
        # Récupérer les utilisateurs avec le rôle du prochain validateur
        if prochain_validateur == "COMPTABLE":
            type_notif = TypeNotificationEnum.BESOIN_VALIDE
        elif prochain_validateur == "CAISSE":
            type_notif = TypeNotificationEnum.BESOIN_VALIDE
        elif prochain_validateur == "DG":
            type_notif = TypeNotificationEnum.BESOIN_VALIDE
        else:
            type_notif = TypeNotificationEnum.BESOIN_CREE
        
        # Notifier par rôle
        self.envoyer_notification_par_role(
            role_nom=prochain_validateur,
            type_notif=type_notif,
            titre=titre,
            contenu=contenu,
            lien=f"/validations/{objet_type.lower()}s/{objet_id}"
        )

    def notifier_cession_eligible(self, bien_id: int, eligibilite: dict):
        """
        Notifie qu'un bien est éligible à la cession.
        """
        if not eligibilite.get("est_eligible", False):
            return
        
        # Récupérer la désignation du bien
        from ..models.bien import Bien
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        designation = "Bien"
        if bien:
            if hasattr(bien, 'marque') and bien.marque:
                designation = f"{bien.marque} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
            elif hasattr(bien, 'fabricant') and bien.fabricant:
                designation = f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
            else:
                designation = f"Bien #{bien_id}"
        
        # Notifier le gestionnaire de parc (DG)
        self.envoyer_notification_par_role(
            role_nom="DG",
            type_notif=TypeNotificationEnum.ALERTE_VNC_ZERO,
            titre=f"🔔 Bien éligible à la cession - {designation}",
            contenu=f"Le bien '{designation}' est éligible à la cession. {eligibilite.get('recommandation', '')}",
            lien=f"/biens/{bien_id}/cession"
        )
        
        # Notifier le comptable
        self.envoyer_notification_par_role(
            role_nom="COMPTABLE",
            type_notif=TypeNotificationEnum.ALERTE_STOCK,
            titre=f"💰 Bien éligible à la cession - {designation}",
            contenu=f"Le bien '{designation}' est éligible à la cession. Veuillez préparer les écritures comptables.",
            lien=f"/biens/{bien_id}/cession"
        )
        
        # Notifier l'administrateur
        self.envoyer_notification_par_role(
            role_nom="ADMIN",
            type_notif=TypeNotificationEnum.ALERTE_STOCK,
            titre=f"📋 Bien éligible à la cession - {designation}",
            contenu=f"Le bien '{designation}' est éligible à la cession. Une action est requise.",
            lien=f"/biens/{bien_id}/cession"
        )
        
        logger.info("Notifications de cession éligible envoyées pour le bien %s", bien_id)

    # ============================================================
    # MÉTHODES TÂCHE 3 - NOTIFICATIONS MAINTENANCE PRÉDICTIVE
    # ============================================================

    def envoyer_alerte_techniciens(self, type_alerte: str, message: str, bien_id: int):
        """
        Envoie une alerte à tous les techniciens
        """
        techniciens = self.db.query(Utilisateur).join(
            Utilisateur.roles
        ).filter(
            Role.nom == "TECHNICIEN"
        ).all()
        
        if not techniciens:
            logger.warning("Aucun technicien trouvé pour l'alerte")
            return
        
        # Déterminer le type de notification
        if "critique" in type_alerte.lower() or "MAINTENANCE_ALERTE" in type_alerte:
            type_notif = TypeNotificationEnum.MAINTENANCE_ALERTE
            priorite = "critique"
        elif "planifiee" in type_alerte.lower():
            type_notif = TypeNotificationEnum.MAINTENANCE_PLANIFIEE
            priorite = "importante"
        else:
            type_notif = TypeNotificationEnum.MAINTENANCE_PLANIFIEE
            priorite = "normale"
        
        # Notifier tous les techniciens
        for tech in techniciens:
            notification = Notification(
                type_notification=type_notif,
                titre=f"🔧 {type_alerte} - Bien #{bien_id}",
                contenu=message,
                lien_action=f"/biens/{bien_id}",
                priorite=priorite,
                date_creation=datetime.now(timezone.utc)
            )
            self.db.add(notification)
            self.db.flush()
            
            # Lier la notification à l'utilisateur
            self.db.execute(
                notification_user.insert().values(
                    id_notification=notification.id_notification,
                    id_utilisateur=tech.id,
                    est_lu=False,
                    date_lecture=None,
                    est_archivee=False,
                )
            )
        
        self.db.commit()
        logger.info("Alerte techniciens envoyée: %s à %s technicien(s)", type_alerte, len(techniciens))
    
    def envoyer_alerte_dg(self, message: str, bien_id: int):
        """
        Envoie une alerte au Directeur Général
        """
        dg = self.db.query(Utilisateur).join(
            Utilisateur.roles
        ).filter(
            Role.nom == "DG"
        ).first()
        
        if dg:
            notification = Notification(
                type_notification=TypeNotificationEnum.ALERTE_VNC_ZERO,
                titre=f"🚨 ALERTE CRITIQUE - Bien #{bien_id}",
                contenu=message,
                lien_action=f"/biens/{bien_id}",
                priorite="critique",
                date_creation=datetime.now(timezone.utc)
            )
            self.db.add(notification)
            self.db.flush()
            
            # Lier la notification à l'utilisateur
            self.db.execute(
                notification_user.insert().values(
                    id_notification=notification.id_notification,
                    id_utilisateur=dg.id,
                    est_lu=False,
                    date_lecture=None,
                    est_archivee=False,
                )
            )
            
            self.db.commit()
            
            # Envoyer également par email si configuré
            if dg.email:
                self._envoyer_email(
                    dg.id,
                    "🚨 ALERTE CRITIQUE - Remplacement de bien requis",
                    message,
                    f"/biens/{bien_id}"
                )
            
            logger.info("Alerte DG envoyée pour le bien %s", bien_id)
        else:
            logger.warning("Aucun DG trouvé pour l'alerte")
    
    def envoyer_alerte_maintenance_auto(self, bien_id: int, score_fiabilite: float):
        """
        Envoie une alerte pour une maintenance automatique générée
        """
        # Récupérer la désignation du bien
        from ..models.bien import Bien
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        designation = "Bien"
        if bien:
            if hasattr(bien, 'marque') and bien.marque:
                designation = f"{bien.marque} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
            elif hasattr(bien, 'fabricant') and bien.fabricant:
                designation = f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
            else:
                designation = f"Bien #{bien_id}"
        
        # Message pour les techniciens
        message_tech = f"Maintenance préventive automatique planifiée pour {designation} (Score: {score_fiabilite:.1f}%)"
        
        # Envoyer aux techniciens
        self.envoyer_alerte_techniciens(
            type_alerte="MAINTENANCE_AUTO",
            message=message_tech,
            bien_id=bien_id
        )
        
        # Envoyer au DG
        message_dg = f"Une maintenance préventive automatique a été générée pour {designation} (Score: {score_fiabilite:.1f}%)"
        self.envoyer_alerte_dg(message_dg, bien_id)
        
        logger.info("Alertes maintenance auto envoyées pour le bien %s", bien_id)
    
    def envoyer_alerte_vnc(self, bien_id: int, seuil: str, ratio: float, vnc: float):
        """
        Envoie une alerte VNC au DG et au Comptable
        """
        # Récupérer la désignation du bien
        from ..models.bien import Bien
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        designation = "Bien"
        if bien:
            if hasattr(bien, 'marque') and bien.marque:
                designation = f"{bien.marque} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
            elif hasattr(bien, 'fabricant') and bien.fabricant:
                designation = f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
            else:
                designation = f"Bien #{bien_id}"
        
        message = f"Le bien {designation} a atteint le seuil VNC de {seuil}% (Ratio: {ratio*100:.1f}%, VNC: {vnc:.2f} USD). Remplacement recommandé."
        
        # Envoyer au DG
        self.envoyer_alerte_dg(message, bien_id)
        
        # Envoyer au Comptable
        comptables = self.db.query(Utilisateur).join(
            Utilisateur.roles
        ).filter(
            Role.nom == "COMPTABLE"
        ).all()
        
        if comptables:
            for comptable in comptables:
                notification = Notification(
                    type_notification=TypeNotificationEnum.ALERTE_STOCK,
                    titre=f"💰 Alerte VNC - {designation}",
                    contenu=message,
                    lien_action=f"/biens/{bien_id}/amortissement",
                    priorite="importante",
                    date_creation=datetime.now(timezone.utc)
                )
                self.db.add(notification)
                self.db.flush()
                
                self.db.execute(
                    notification_user.insert().values(
                        id_notification=notification.id_notification,
                        id_utilisateur=comptable.id,
                        est_lu=False,
                        date_lecture=None,
                        est_archivee=False,
                    )
                )
            
            self.db.commit()
            logger.info("Alerte VNC envoyée au comptable pour le bien %s", bien_id)
    
    def envoyer_alerte_remplacement(self, bien_id: int, bien_nouveau_id: int = None):
        """
        Envoie une alerte de remplacement de bien
        """
        from ..models.bien import Bien
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        designation = "Bien"
        if bien:
            if hasattr(bien, 'marque') and bien.marque:
                designation = f"{bien.marque} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
            elif hasattr(bien, 'fabricant') and bien.fabricant:
                designation = f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
            else:
                designation = f"Bien #{bien_id}"
        
        message = f"Le bien {designation} a été marqué pour remplacement."
        if bien_nouveau_id:
            nouveau_bien = self.db.query(Bien).filter(Bien.id_bien == bien_nouveau_id).first()
            if nouveau_bien:
                nouveau_designation = "Bien"
                if hasattr(nouveau_bien, 'marque') and nouveau_bien.marque:
                    nouveau_designation = f"{nouveau_bien.marque} {getattr(nouveau_bien, 'modele', '')}".strip() or f"Bien #{bien_nouveau_id}"
                elif hasattr(nouveau_bien, 'fabricant') and nouveau_bien.fabricant:
                    nouveau_designation = f"{nouveau_bien.fabricant} {getattr(nouveau_bien, 'modele', '')}".strip() or f"Bien #{bien_nouveau_id}"
                message += f" Remplacé par: {nouveau_designation}"
        
        # Envoyer au DG
        self.envoyer_alerte_dg(message, bien_id)
        
        # Envoyer au Comptable
        comptables = self.db.query(Utilisateur).join(
            Utilisateur.roles
        ).filter(
            Role.nom == "COMPTABLE"
        ).all()
        
        if comptables:
            for comptable in comptables:
                notification = Notification(
                    type_notification=TypeNotificationEnum.ALERTE_STOCK,
                    titre=f"🔄 Remplacement de bien - {designation}",
                    contenu=message,
                    lien_action=f"/biens/{bien_id}",
                    priorite="importante",
                    date_creation=datetime.now(timezone.utc)
                )
                self.db.add(notification)
                self.db.flush()
                
                self.db.execute(
                    notification_user.insert().values(
                        id_notification=notification.id_notification,
                        id_utilisateur=comptable.id,
                        est_lu=False,
                        date_lecture=None,
                        est_archivee=False,
                    )
                )
            
            self.db.commit()
            logger.info("Alerte remplacement envoyée pour le bien %s", bien_id)