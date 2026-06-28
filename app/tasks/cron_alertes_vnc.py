# backend/app/tasks/cron_alertes_vnc.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

from ..services.amortissement_service import AmortissementService
from ..services.notification_service import NotificationService
from ..services.ordre_remplacement_service import OrdreRemplacementService
from ..core.database import SessionLocal
from ..core.constants import CRON_VNC_HOUR, CRON_VNC_MINUTE
from ..models.notification import TypeNotificationEnum

logger = logging.getLogger(__name__)


def verifier_alertes_vnc():
    """
    Tâche CRON exécutée chaque nuit à 03h00.
    Vérifie les seuils VNC pour les biens actifs.
    """
    logger.info("=" * 60)
    logger.info(f"🚀 Début de la vérification des seuils VNC - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        service = AmortissementService(db)
        notification_service = NotificationService(db)
        ordre_service = OrdreRemplacementService(db)

        # ✅ Récupérer uniquement les biens à vérifier
        biens_ids = service.get_biens_a_verifier_vnc(limite=1000)

        if not biens_ids:
            logger.info("   ℹ️ Aucun bien à vérifier")
            return {
                "total_biens": 0,
                "alertes_generees": 0,
                "biens_critiques": 0,
                "biens_standards": 0,
                "message": "Aucun bien à vérifier"
            }

        logger.info(f"   📊 {len(biens_ids)} bien(s) à vérifier")

        alertes_generees = 0
        biens_critiques = 0
        biens_standards = 0
        succes = 0
        echecs = 0
        erreurs = []

        for bien_id in biens_ids:
            try:
                # ✅ Session isolée par bien
                db_bien = SessionLocal()
                service_bien = AmortissementService(db_bien)

                try:
                    alerte = service_bien.verifier_seuils_vnc(bien_id)
                    if alerte:
                        alertes_generees += 1

                    # Récupérer le bien pour les statistiques
                    bien = db_bien.query(Bien).filter(Bien.id_bien == bien_id).first()
                    if bien:
                        if bien.est_critique:
                            biens_critiques += 1
                        else:
                            biens_standards += 1

                    succes += 1

                except Exception as e:
                    echecs += 1
                    erreurs.append(f"Bien {bien_id}: {str(e)}")
                    logger.error(f"❌ Erreur VNC bien {bien_id}: {e}")

                finally:
                    db_bien.close()

            except Exception as e:
                echecs += 1
                logger.error(f"❌ Erreur critique bien {bien_id}: {e}")

        total = succes + echecs
        resultats = {
            "total_biens": total,
            "alertes_generees": alertes_generees,
            "biens_critiques": biens_critiques,
            "biens_standards": biens_standards,
            "echecs": echecs,
            "erreurs": erreurs[:5]
        }

        # Journaliser les résultats
        logger.info(f"✅ Vérification VNC terminée")
        logger.info(f"   📊 Total biens vérifiés: {total}")
        logger.info(f"   🔴 Biens critiques: {biens_critiques}")
        logger.info(f"   🟢 Biens standards: {biens_standards}")
        logger.info(f"   ⚠️ Alertes générées: {alertes_generees}")
        if echecs > 0:
            logger.warning(f"   ❌ Échecs: {echecs}")

        # ✅ Notification si taux d'échec élevé
        taux_echec = (echecs / total * 100) if total > 0 else 0
        if taux_echec > 20:
            notification_service.envoyer_notification_par_role(
                role_nom="ADMIN",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre="⚠️ CRON VNC - Taux d'échec élevé",
                contenu=f"Taux d'échec: {taux_echec:.1f}% ({echecs}/{total} biens)",
                lien="/logs"
            )

        # ✅ Si des alertes ont été générées, envoyer des notifications
        if alertes_generees > 0:
            notification_service.envoyer_notification_par_role(
                role_nom="DG",
                type_notif=TypeNotificationEnum.ALERTE_VNC_ZERO,
                titre=f"🚨 {alertes_generees} alerte(s) VNC détectée(s)",
                contenu=f"{alertes_generees} bien(s) ont atteint leur seuil VNC critique. Des ordres de remplacement ont été générés.",
                lien="/alertes-vnc"
            )

            notification_service.envoyer_notification_par_role(
                role_nom="COMPTABLE",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre=f"💰 {alertes_generees} alerte(s) VNC - Action requise",
                contenu=f"{alertes_generees} bien(s) ont atteint leur seuil VNC critique. Veuillez préparer les écritures comptables.",
                lien="/alertes-vnc"
            )

            # ✅ Vérifier les ordres en retard après les alertes
            try:
                ordres_retard = ordre_service.verifier_et_relancer_ordres_en_retard()
                if ordres_retard['total_en_retard'] > 0:
                    logger.info(f"   📬 Relances envoyées pour {ordres_retard['relances_envoyees']} ordre(s) en retard")
            except Exception as e:
                logger.warning(f"Erreur vérification ordres en retard: {e}")

        return resultats

    except Exception as e:
        logger.error(f"❌ Erreur lors de la vérification VNC: {str(e)}")
        logger.exception("Détails de l'erreur:")

        try:
            notification_service = NotificationService(db)
            notification_service.envoyer_notification_par_role(
                role_nom="ADMIN",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre="🚨 ERREUR - Vérification des seuils VNC",
                contenu=f"Une erreur est survenue lors de la vérification des seuils VNC: {str(e)}",
                lien="/logs"
            )
        except:
            pass

        raise
    finally:
        db.close()
        logger.info("=" * 60)
        logger.info("🏁 Fin de la vérification des seuils VNC")
        logger.info("=" * 60)


def init_scheduler(scheduler: BackgroundScheduler = None):
    """
    Initialise le scheduler pour les tâches CRON des alertes VNC.
    """
    if scheduler is None:
        scheduler = BackgroundScheduler()

    existing_job = scheduler.get_job('verifier_alertes_vnc')
    if existing_job:
        scheduler.remove_job('verifier_alertes_vnc')

    scheduler.add_job(
        verifier_alertes_vnc,
        trigger=CronTrigger(hour=CRON_VNC_HOUR, minute=CRON_VNC_MINUTE),
        id='verifier_alertes_vnc',
        name='Vérification des seuils VNC',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600
    )

    logger.info(f"🔄 Scheduler des alertes VNC configuré à {CRON_VNC_HOUR:02d}h{CRON_VNC_MINUTE:02d}")

    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Scheduler démarré")

    return scheduler


def run_manually():
    """Exécute manuellement la tâche de vérification VNC (pour les tests)."""
    logger.info("🔄 Exécution manuelle de la vérification des seuils VNC")
    return verifier_alertes_vnc()


# ✅ Importer Bien pour le type hint
from ..models.bien import Bien