# backend/app/tasks/cron_scores.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import time

from ..services.maintenance_service import MaintenanceService
from ..services.notification_service import NotificationService
from ..core.database import SessionLocal
from ..core.constants import CRON_SCORE_HOUR, CRON_SCORE_MINUTE
from ..models.notification import TypeNotificationEnum

logger = logging.getLogger(__name__)


def calculer_scores_fiabilite():
    """
    Tâche CRON exécutée chaque nuit à 02h00.
    Calcule les scores de fiabilité pour les biens marqués à recalculer.
    """
    logger.info("=" * 60)
    logger.info(f"🚀 Début du calcul des scores de fiabilité - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        service = MaintenanceService(db)
        notification_service = NotificationService(db)

        # ✅ Récupérer uniquement les biens marqués à recalculer
        biens_ids = service.get_biens_a_recalculer(limite=500)

        if not biens_ids:
            logger.info("   ℹ️ Aucun bien à recalculer")
            return {
                "total": 0,
                "scores_calcules": 0,
                "maintenances_planifiees": 0,
                "alertes_vnc_generees": 0,
                "message": "Aucun bien à recalculer"
            }

        logger.info(f"   📊 {len(biens_ids)} bien(s) à recalculer")

        succes = 0
        echecs = 0
        erreurs = []
        maintenances_planifiees = 0
        alertes_vnc_generees = 0
        critiques = 0

        for bien_id in biens_ids:
            try:
                # ✅ Session isolée par bien pour éviter les problèmes de transaction
                db_bien = SessionLocal()
                service_bien = MaintenanceService(db_bien)
                notification_bien = NotificationService(db_bien)

                try:
                    # Calculer le score
                    score = service_bien.calculer_score_fiabilite(bien_id)
                    succes += 1

                    # Vérifier si une maintenance auto est nécessaire
                    try:
                        maintenance = service_bien.verifier_et_planifier_maintenance_auto(bien_id)
                        if maintenance:
                            maintenances_planifiees += 1
                    except Exception as e:
                        logger.warning(f"Erreur maintenance auto bien {bien_id}: {e}")

                    # Vérifier les seuils VNC
                    try:
                        alerte = service_bien.verifier_et_creer_alerte_vnc(bien_id)
                        if alerte:
                            alertes_vnc_generees += 1
                    except Exception as e:
                        logger.warning(f"Erreur alerte VNC bien {bien_id}: {e}")

                    # Récupérer le bien pour vérifier s'il est critique
                    bien = db_bien.query(Bien).filter(Bien.id_bien == bien_id).first()
                    if bien and bien.est_critique:
                        critiques += 1

                except Exception as e:
                    echecs += 1
                    erreurs.append(f"Bien {bien_id}: {str(e)}")
                    logger.error(f"❌ Erreur score bien {bien_id}: {e}")

                finally:
                    db_bien.close()

            except Exception as e:
                echecs += 1
                logger.error(f"❌ Erreur critique bien {bien_id}: {e}")

        total = succes + echecs
        resultats = {
            "total": total,
            "critiques": critiques,
            "maintenances_planifiees": maintenances_planifiees,
            "alertes_vnc_generees": alertes_vnc_generees,
            "scores_calcules": succes,
            "echecs": echecs,
            "erreurs": erreurs[:5]  # Limiter pour le log
        }

        # Journaliser les résultats
        logger.info(f"✅ Scores calculés avec succès")
        logger.info(f"   📊 Total biens traités: {total}")
        logger.info(f"   🔴 Biens critiques: {critiques}")
        logger.info(f"   🔧 Maintenances planifiées: {maintenances_planifiees}")
        logger.info(f"   ⚠️ Alertes VNC générées: {alertes_vnc_generees}")
        logger.info(f"   📈 Scores calculés: {succes}")
        if echecs > 0:
            logger.warning(f"   ❌ Échecs: {echecs}")
            for err in erreurs[:3]:
                logger.warning(f"      - {err}")

        # ✅ Notification si taux d'échec élevé
        taux_echec = (echecs / total * 100) if total > 0 else 0
        if taux_echec > 20:
            notification_service.envoyer_notification_par_role(
                role_nom="ADMIN",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre="⚠️ CRON Scores - Taux d'échec élevé",
                contenu=f"Taux d'échec: {taux_echec:.1f}% ({echecs}/{total} biens)",
                lien="/logs"
            )

        # ✅ Notification de synthèse
        if maintenances_planifiees > 0 or alertes_vnc_generees > 0:
            notification_service.envoyer_notification_par_role(
                role_nom="DG",
                type_notif=TypeNotificationEnum.MAINTENANCE_ALERTE,
                titre="📊 Rapport quotidien - Scores de fiabilité",
                contenu=(
                    f"Synthèse du calcul des scores de fiabilité du {datetime.now().strftime('%d/%m/%Y')}:\n"
                    f"- {total} biens analysés\n"
                    f"- {critiques} biens critiques\n"
                    f"- {maintenances_planifiees} maintenances préventives auto-générées\n"
                    f"- {alertes_vnc_generees} alertes VNC déclenchées"
                ),
                lien="/tableau-de-bord"
            )

        if maintenances_planifiees > 0:
            notification_service.envoyer_notification_par_role(
                role_nom="TECHNICIEN",
                type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                titre=f"🔧 {maintenances_planifiees} maintenance(s) préventive(s) auto-générée(s)",
                contenu=f"{maintenances_planifiees} maintenance(s) préventive(s) ont été automatiquement planifiées suite au calcul des scores de fiabilité.",
                lien="/maintenances"
            )

        return resultats

    except Exception as e:
        logger.error(f"❌ Erreur lors du calcul des scores: {str(e)}")
        logger.exception("Détails de l'erreur:")

        try:
            notification_service = NotificationService(db)
            notification_service.envoyer_notification_par_role(
                role_nom="ADMIN",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre="🚨 ERREUR - Calcul des scores de fiabilité",
                contenu=f"Une erreur est survenue lors du calcul des scores de fiabilité: {str(e)}",
                lien="/logs"
            )
        except:
            pass

        raise
    finally:
        db.close()
        logger.info("=" * 60)
        logger.info("🏁 Fin du calcul des scores de fiabilité")
        logger.info("=" * 60)


def init_scheduler(scheduler: BackgroundScheduler = None):
    """
    Initialise le scheduler pour les tâches CRON des scores de fiabilité.
    """
    if scheduler is None:
        scheduler = BackgroundScheduler()

    existing_job = scheduler.get_job('calcul_scores_fiabilite')
    if existing_job:
        scheduler.remove_job('calcul_scores_fiabilite')

    scheduler.add_job(
        calculer_scores_fiabilite,
        trigger=CronTrigger(hour=CRON_SCORE_HOUR, minute=CRON_SCORE_MINUTE),
        id='calcul_scores_fiabilite',
        name='Calcul des scores de fiabilité',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600
    )

    logger.info(f"🔄 Scheduler des scores de fiabilité configuré à {CRON_SCORE_HOUR:02d}h{CRON_SCORE_MINUTE:02d}")

    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Scheduler démarré")

    return scheduler


def run_manually():
    """Exécute manuellement la tâche de calcul des scores (pour les tests)."""
    logger.info("🔄 Exécution manuelle du calcul des scores de fiabilité")
    return calculer_scores_fiabilite()


# ✅ Importer Bien pour le type hint
from ..models.bien import Bien