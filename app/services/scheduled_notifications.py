# backend/app/services/scheduled_notifications.py
import logging
from sqlalchemy.orm import Session
from datetime import datetime

from ..core.database import SessionLocal
from .notification_trigger_service import NotificationTriggerService
from .concertation_service import ConcertationService
from ..models.discussion_concertation import DiscussionConcertation
from ..models.notification import TypeNotificationEnum
from ..schemas.concertation import DiscussionConcertationCreate, MessageConcertationCreate

logger = logging.getLogger(__name__)

def run_maintenance_alert_check():
    db = SessionLocal()
    try:
        trigger_service = NotificationTriggerService(db)
        notifications = trigger_service.verifier_alertes_maintenance()
        logger.info(f"Alertes maintenance envoyées: {len(notifications)}")
    except Exception as e:
        logger.error(f"Erreur vérification maintenance: {e}")
    finally:
        db.close()

def run_vnc_zero_check():
    db = SessionLocal()
    try:
        trigger_service = NotificationTriggerService(db)
        notifications = trigger_service.verifier_vnc_zero()
        logger.info(f"Alertes VNC zéro envoyées: {len(notifications)}")
    except Exception as e:
        logger.error(f"Erreur vérification VNC zéro: {e}")
    finally:
        db.close()

def run_missing_amortissement_check():
    db = SessionLocal()
    try:
        trigger_service = NotificationTriggerService(db)
        notifications = trigger_service.verifier_amortissements_manquants()
        logger.info(f"Rappels amortissement envoyés: {len(notifications)}")
    except Exception as e:
        logger.error(f"Erreur vérification amortissements: {e}")
    finally:
        db.close()

def run_detection_biens_eligibles():
    db = SessionLocal()
    try:
        service = ConcertationService(db)
        biens_eligibles = service.detecter_biens_eligibles()
        
        for bien in biens_eligibles:
            existing = db.query(DiscussionConcertation).filter(
                DiscussionConcertation.id_bien == bien["id_bien"],
                DiscussionConcertation.est_active == True
            ).first()
            
            if existing:
                continue
            
            type_validation = "REBUT" if bien["type_recommande"] == "REBUT" else "CESSION"
            titre = f"Proposition de {type_validation} - {bien['designation']}"
            
            try:
                data = DiscussionConcertationCreate(
                    id_bien=bien["id_bien"],
                    type_validation=type_validation,
                    titre=titre
                )
                
                discussion = service.creer_discussion(data, id_createur=1)
                
                message_data = MessageConcertationCreate(
                    contenu=f"🤖 Détection automatique : {bien['motif']}\n\n"
                            f"📊 Informations :\n"
                            f"• Prix d'acquisition : {bien['prix_acquisition']:.2f} USD\n"
                            f"• Coût maintenance : {bien['cout_maintenance']:.2f} USD\n"
                            f"• Nombre de pannes : {bien['nb_pannes']}\n"
                            f"• VNC : {bien['vnc']:.2f} USD\n"
                            f"• Ratio VNC : {bien['ratio_vnc']*100:.1f}%\n"
                            f"• Diagnostic irrécupérable : {'✅ Oui' if bien['diagnostic_irrecuperable'] else '❌ Non'}\n\n"
                            f"📋 Action recommandée : {type_validation}\n"
                            f"Veuillez analyser cette proposition et valider conjointement."
                )
                service.ajouter_message(discussion.id, message_data, id_createur=1)
                
                logger.info(f"Discussion automatique créée pour le bien {bien['id_bien']} - {type_validation}")
            except Exception as e:
                logger.error(f"Erreur création discussion auto pour bien {bien['id_bien']}: {e}")
        
        logger.info(f"Détection terminée : {len(biens_eligibles)} bien(s) éligible(s)")
    except Exception as e:
        logger.error(f"Erreur détection biens éligibles: {e}")
    finally:
        db.close()