# backend/app/services/scheduled_notifications.py
"""Tâches planifiées pour les notifications automatiques"""
import logging
from sqlalchemy.orm import Session
from datetime import datetime

from ..core.database import SessionLocal
from .notification_trigger_service import NotificationTriggerService

logger = logging.getLogger(__name__)

def run_maintenance_alert_check():
    """Vérifie les maintenances à J+2 (à exécuter quotidiennement)"""
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
    """Vérifie les VNC à zéro (à exécuter quotidiennement)"""
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
    """Vérifie les amortissements manquants (à exécuter mensuellement)"""
    db = SessionLocal()
    try:
        trigger_service = NotificationTriggerService(db)
        notifications = trigger_service.verifier_amortissements_manquants()
        logger.info(f"Rappels amortissement envoyés: {len(notifications)}")
    except Exception as e:
        logger.error(f"Erreur vérification amortissements: {e}")
    finally:
        db.close()