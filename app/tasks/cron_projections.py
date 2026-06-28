# backend/app/tasks/cron_projections.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

from ..services.maintenance_service import MaintenanceService
from ..services.notification_service import NotificationService
from ..core.database import SessionLocal
from ..core.constants import CRON_PROJECTION_HOUR, CRON_PROJECTION_MINUTE
from ..models.notification import TypeNotificationEnum
from ..models.bien import Bien

logger = logging.getLogger(__name__)


def generer_projections():
    """
    Tâche CRON exécutée chaque nuit à 04h00.
    Génère les projections d'investissement N+1 à N+5 pour les biens actifs.
    """
    logger.info("=" * 60)
    logger.info(f"🚀 Début de la génération des projections pluriannuelles - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        notification_service = NotificationService(db)
        annee_actuelle = datetime.now().year

        # ✅ Récupérer tous les biens actifs
        biens = db.query(Bien).filter(
            Bien.statut_comptable == 'ACTIF'
        ).all()

        if not biens:
            logger.info("   ℹ️ Aucun bien à projeter")
            return {
                "total_biens": 0,
                "projections_calculees": 0,
                "biens_a_remplacer": [],
                "message": "Aucun bien actif"
            }

        logger.info(f"   📊 {len(biens)} bien(s) à traiter")

        succes = 0
        echecs = 0
        erreurs = []
        total_projections = 0
        biens_a_remplacer = []

        for bien in biens:
            try:
                # ✅ Session isolée par bien
                db_bien = SessionLocal()
                service_bien = MaintenanceService(db_bien)

                try:
                    projections = service_bien.generer_projections_bien(bien.id_bien)
                    total_projections += len(projections)
                    succes += 1

                    # ✅ Vérifier si le bien doit être remplacé dans les 2 ans
                    for proj in projections:
                        if proj.annee_projection <= datetime.now().year + 2:
                            if proj.critere_fin_amortissement or proj.critere_score_fiabilite:
                                designation = f"{getattr(bien, 'marque', '') or getattr(bien, 'fabricant', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
                                biens_a_remplacer.append({
                                    "bien_id": bien.id_bien,
                                    "designation": designation,
                                    "annee": proj.annee_projection,
                                    "cout_remplacement": float(proj.cout_remplacement_estime or 0),
                                    "raison": "Amortissement complet" if proj.critere_fin_amortissement else "Score de fiabilité critique"
                                })
                                break

                except Exception as e:
                    echecs += 1
                    erreurs.append(f"Bien {bien.id_bien}: {str(e)}")
                    logger.error(f"❌ Erreur projection bien {bien.id_bien}: {e}")

                finally:
                    db_bien.close()

            except Exception as e:
                echecs += 1
                logger.error(f"❌ Erreur critique bien {bien.id_bien}: {e}")

        total = succes + echecs
        resultats = {
            "total_biens": len(biens),
            "projections_calculees": total_projections,
            "biens_a_remplacer": biens_a_remplacer,
            "succes": succes,
            "echecs": echecs,
            "erreurs": erreurs[:5]
        }

        # Journaliser les résultats
        logger.info(f"✅ Projections générées avec succès")
        logger.info(f"   📊 Total biens traités: {total}")
        logger.info(f"   📈 Projections calculées: {total_projections}")
        logger.info(f"   🔄 Biens à remplacer: {len(biens_a_remplacer)}")
        if echecs > 0:
            logger.warning(f"   ❌ Échecs: {echecs}")

        # ✅ Notification si taux d'échec élevé
        taux_echec = (echecs / total * 100) if total > 0 else 0
        if taux_echec > 20:
            notification_service.envoyer_notification_par_role(
                role_nom="ADMIN",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre="⚠️ CRON Projections - Taux d'échec élevé",
                contenu=f"Taux d'échec: {taux_echec:.1f}% ({echecs}/{total} biens)",
                lien="/logs"
            )

        # ✅ Envoyer une notification au DG si des biens sont à remplacer
        if biens_a_remplacer:
            total_cout = sum(b["cout_remplacement"] for b in biens_a_remplacer)
            notification_service.envoyer_notification_par_role(
                role_nom="DG",
                type_notif=TypeNotificationEnum.RAPPEL_AMORTISSEMENT_MANQUANT,
                titre="📊 Projections d'investissement N+1 à N+5",
                contenu=(
                    f"Projections pluriannuelles générées le {datetime.now().strftime('%d/%m/%Y')}:\n"
                    f"- {len(biens_a_remplacer)} biens à remplacer dans les 2 ans\n"
                    f"- Coût total estimé: {total_cout:,.0f} FCFA\n"
                    f"- Consultez le rapport détaillé pour plus d'informations."
                ),
                lien="/rapports/projections"
            )

            notification_service.envoyer_notification_par_role(
                role_nom="COMPTABLE",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre=f"💰 Projections d'investissement - {annee_actuelle}",
                contenu=(
                    f"Les projections d'investissement pour les 5 prochaines années ont été générées.\n"
                    f"{len(biens_a_remplacer)} biens sont identifiés pour remplacement dans les 2 ans."
                ),
                lien="/rapports/projections"
            )

        return resultats

    except Exception as e:
        logger.error(f"❌ Erreur lors de la génération des projections: {str(e)}")
        logger.exception("Détails de l'erreur:")

        try:
            notification_service = NotificationService(db)
            notification_service.envoyer_notification_par_role(
                role_nom="ADMIN",
                type_notif=TypeNotificationEnum.ALERTE_STOCK,
                titre="🚨 ERREUR - Génération des projections",
                contenu=f"Une erreur est survenue lors de la génération des projections: {str(e)}",
                lien="/logs"
            )
        except:
            pass

        raise
    finally:
        db.close()
        logger.info("=" * 60)
        logger.info("🏁 Fin de la génération des projections")
        logger.info("=" * 60)


def init_scheduler(scheduler: BackgroundScheduler = None):
    """
    Initialise le scheduler pour les tâches CRON des projections.
    """
    if scheduler is None:
        scheduler = BackgroundScheduler()

    existing_job = scheduler.get_job('generer_projections')
    if existing_job:
        scheduler.remove_job('generer_projections')

    scheduler.add_job(
        generer_projections,
        trigger=CronTrigger(hour=CRON_PROJECTION_HOUR, minute=CRON_PROJECTION_MINUTE),
        id='generer_projections',
        name='Génération des projections d\'investissement',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600
    )

    logger.info(f"🔄 Scheduler des projections configuré à {CRON_PROJECTION_HOUR:02d}h{CRON_PROJECTION_MINUTE:02d}")

    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Scheduler démarré")

    return scheduler


def run_manually():
    """Exécute manuellement la tâche de génération des projections (pour les tests)."""
    logger.info("🔄 Exécution manuelle de la génération des projections")
    return generer_projections()