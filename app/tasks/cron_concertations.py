# app/tasks/cron_concertations.py
"""
Tâche CRON : détection automatique des biens éligibles au rebut/cession
et création des discussions de concertation correspondantes.

Fréquence par défaut : toutes les 6 heures.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def detecter_et_creer_discussions():
    """
    Point d'entrée du job CRON.
    Ouvre sa propre session BDD, appelle ConcertationService.creer_discussions_automatiques()
    et journalise le résultat.
    """
    from app.core.database import SessionLocal
    from app.services.concertation_service import ConcertationService

    db = SessionLocal()
    try:
        logger.info("[CRON] Début détection automatique biens éligibles concertation...")
        service = ConcertationService(db)
        resultat = service.creer_discussions_automatiques()
        logger.info(
            f"[CRON] Détection terminée — "
            f"{resultat['total_eligibles']} éligibles, "
            f"{resultat['creees']} discussion(s) créée(s), "
            f"{resultat['ignorees']} ignorée(s), "
            f"{resultat['erreurs']} erreur(s)"
        )
    except Exception as exc:
        logger.error(f"[CRON] Erreur lors de la détection automatique : {exc}", exc_info=True)
    finally:
        db.close()


def init_scheduler(scheduler):
    """
    Enregistre le job dans le scheduler APScheduler partagé.
    Tournera toutes les 6 heures (modifiable via l'argument 'hours').
    """
    scheduler.add_job(
        detecter_et_creer_discussions,
        trigger="interval",
        hours=6,
        id="cron_detecter_concertations",
        name="Détection auto biens éligibles concertation",
        replace_existing=True,
        next_run_time=datetime.now(),   # Exécution immédiate au démarrage
    )
    logger.info("[CRON] Job 'détection concertations' enregistré (toutes les 6h)")
    return scheduler
