import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from sqlalchemy import and_, text

from ..core.database import SessionLocal
from ..core.redis_client import redis_client
from ..core.config import settings
from ..models.session import SessionUtilisateur

logger = logging.getLogger(__name__)


class CleanupService:
    """
    Service de nettoyage automatique des sessions.
    Gère les jobs planifiés pour le nettoyage BDD et Redis.
    """
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.is_running = False
    
    def start(self):
        """
        Démarre le service de nettoyage avec tous les jobs planifiés.
        """
        if self.is_running:
            logger.warning("CleanupService déjà en cours d'exécution")
            return
        
        try:
            # Job 1 : Nettoyage BDD (toutes les heures)
            self.scheduler.add_job(
                self._cleanup_database,
                trigger=IntervalTrigger(hours=1),
                id="cleanup_database",
                name="Nettoyage BDD des sessions",
                replace_existing=True
            )
            
            # Job 2 : Nettoyage Redis (toutes les 6 heures)
            self.scheduler.add_job(
                self._cleanup_redis,
                trigger=IntervalTrigger(hours=6),
                id="cleanup_redis",
                name="Nettoyage Redis des sessions",
                replace_existing=True
            )
            
            # Job 3 : Vérification de sécurité (toutes les 24 heures)
            self.scheduler.add_job(
                self._security_check,
                trigger=CronTrigger(hour=2, minute=0),  # 2h du matin
                id="security_check",
                name="Vérification de sécurité",
                replace_existing=True
            )
            
            # Job 4 : Statistiques (toutes les 24 heures)
            self.scheduler.add_job(
                self._log_stats,
                trigger=CronTrigger(hour=3, minute=0),  # 3h du matin
                id="log_stats",
                name="Log des statistiques",
                replace_existing=True
            )
            
            self.scheduler.start()
            self.is_running = True
            
            logger.info("✅ CleanupService démarré avec succès")
            logger.info(f"   - Nettoyage BDD : toutes les heures")
            logger.info(f"   - Nettoyage Redis : toutes les 6 heures")
            logger.info(f"   - Vérification sécurité : 2h du matin")
            logger.info(f"   - Statistiques : 3h du matin")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du démarrage de CleanupService: {e}")
            raise
    
    def stop(self):
        """
        Arrête le service de nettoyage.
        """
        if not self.is_running:
            return
        
        try:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("✅ CleanupService arrêté")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'arrêt de CleanupService: {e}")
    
    # ============================================================
    # JOBS DE NETTOYAGE
    # ============================================================
    
    def _cleanup_database(self):
        """
        Job 1 : Nettoyage de la base de données.
        - Supprime les sessions inactives > 30 jours
        - Supprime les sessions révoquées > 7 jours
        - Supprime les sessions orphelines
        """
        logger.info("🔄 Début du nettoyage BDD")
        start_time = time.time()
        
        db = SessionLocal()
        try:
            deleted_count = 0
            
            # 1. Supprimer les sessions actives inactives
            cutoff_active = datetime.utcnow() - timedelta(days=settings.SESSION_RETENTION_DAYS)
            active_deleted = db.query(SessionUtilisateur).filter(
                and_(
                    SessionUtilisateur.est_revoquee == False,
                    SessionUtilisateur.date_derniere_activite < cutoff_active
                )
            ).delete(synchronize_session=False)
            deleted_count += active_deleted
            
            # 2. Supprimer les sessions révoquées anciennes
            cutoff_revoked = datetime.utcnow() - timedelta(days=settings.REVOKED_SESSION_RETENTION_DAYS)
            revoked_deleted = db.query(SessionUtilisateur).filter(
                and_(
                    SessionUtilisateur.est_revoquee == True,
                    SessionUtilisateur.date_fin < cutoff_revoked
                )
            ).delete(synchronize_session=False)
            deleted_count += revoked_deleted
            
            # 3. Supprimer les sessions orphelines (user_id invalide)
            orphan_deleted = db.query(SessionUtilisateur).filter(
                ~SessionUtilisateur.user_id.in_(
                    db.query(text("SELECT id FROM utilisateurs"))
                )
            ).delete(synchronize_session=False)
            deleted_count += orphan_deleted
            
            # Commit les suppressions
            db.commit()
            
            elapsed = (time.time() - start_time) * 1000
            logger.info(
                f"✅ Nettoyage BDD terminé: {deleted_count} sessions supprimées "
                f"({active_deleted} inactives, {revoked_deleted} révoquées, "
                f"{orphan_deleted} orphelines) - {elapsed:.2f}ms"
            )
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Erreur lors du nettoyage BDD: {e}", exc_info=True)
        finally:
            db.close()
    
    def _cleanup_redis(self):
        """
        Job 2 : Nettoyage de Redis.
        - Supprime les sessions Redis orphelines (sans correspondance BDD)
        """
        logger.info("🔄 Début du nettoyage Redis")
        start_time = time.time()
        
        try:
            # Récupérer toutes les clés de sessions en Redis
            keys = redis_client._get_client().keys("session:*")
            if not keys:
                logger.info("✅ Aucune session en Redis")
                return
            
            db = SessionLocal()
            try:
                deleted_count = 0
                
                for key in keys:
                    # Extraire user_id et session_uuid de la clé
                    # Format: session:{user_id}:{session_uuid}
                    parts = key.split(":")
                    if len(parts) >= 3:
                        user_id = int(parts[1])
                        session_uuid = parts[2]
                        
                        # Vérifier si la session existe en BDD
                        session = db.query(SessionUtilisateur).filter(
                            SessionUtilisateur.session_uuid == session_uuid
                        ).first()
                        
                        if not session:
                            # Session orpheline, supprimer de Redis
                            redis_client.delete_session(user_id, session_uuid)
                            deleted_count += 1
                
                elapsed = (time.time() - start_time) * 1000
                logger.info(
                    f"✅ Nettoyage Redis terminé: {deleted_count} sessions orphelines supprimées - {elapsed:.2f}ms"
                )
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Erreur lors du nettoyage Redis: {e}", exc_info=True)
    
    def _security_check(self):
        """
        Job 3 : Vérification de sécurité.
        - Détecte les sessions multiples depuis la même IP
        - Détecte les sessions anormalement anciennes
        """
        logger.info("🔄 Début de la vérification de sécurité")
        
        db = SessionLocal()
        try:
            # 1. Détecter les sessions multiples depuis la même IP
            # (plus de 5 sessions actives depuis la même IP dans les 6 heures)
            recent_cutoff = datetime.utcnow() - timedelta(hours=6)
            
            suspicious_ips = db.query(
                SessionUtilisateur.ip_address,
                SessionUtilisateur.user_id,
                db.func.count(SessionUtilisateur.id).label('session_count')
            ).filter(
                and_(
                    SessionUtilisateur.est_revoquee == False,
                    SessionUtilisateur.date_connexion > recent_cutoff,
                    SessionUtilisateur.ip_address.isnot(None)
                )
            ).group_by(
                SessionUtilisateur.ip_address,
                SessionUtilisateur.user_id
            ).having(
                db.func.count(SessionUtilisateur.id) > 5
            ).all()
            
            if suspicious_ips:
                logger.warning(
                    f"⚠️ {len(suspicious_ips)} cas suspects détectés: sessions multiples depuis la même IP"
                )
                for item in suspicious_ips:
                    logger.warning(
                        f"   IP: {item.ip_address}, User: {item.user_id}, "
                        f"Sessions: {item.session_count}"
                    )
            
            # 2. Détecter les sessions actives > 7 jours
            old_cutoff = datetime.utcnow() - timedelta(days=7)
            old_sessions = db.query(SessionUtilisateur).filter(
                and_(
                    SessionUtilisateur.est_revoquee == False,
                    SessionUtilisateur.date_connexion < old_cutoff
                )
            ).count()
            
            if old_sessions > 0:
                logger.warning(f"⚠️ {old_sessions} sessions actives de plus de 7 jours détectées")
            
            logger.info("✅ Vérification de sécurité terminée")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification de sécurité: {e}", exc_info=True)
        finally:
            db.close()
    
    def _log_stats(self):
        """
        Job 4 : Log des statistiques des sessions.
        """
        logger.info("📊 Log des statistiques des sessions")
        
        db = SessionLocal()
        try:
            # Statistiques BDD
            total = db.query(SessionUtilisateur).count()
            active = db.query(SessionUtilisateur).filter(
                SessionUtilisateur.est_revoquee == False
            ).count()
            revoked = total - active
            
            # Sessions par utilisateur (top 10)
            user_stats = db.query(
                SessionUtilisateur.user_id,
                db.func.count(SessionUtilisateur.id).label('count')
            ).group_by(SessionUtilisateur.user_id).order_by(
                db.func.count(SessionUtilisateur.id).desc()
            ).limit(10).all()
            
            # Statistiques Redis
            redis_stats = redis_client.get_stats() if redis_client.is_healthy() else None
            
            logger.info(
                f"📊 Statistiques: Total={total}, Actives={active}, "
                f"Révoquées={revoked}, Redis={redis_stats.get('sessions', {}).get('total', 0) if redis_stats else 'N/A'}"
            )
            
            if user_stats:
                logger.info("📊 Top 10 utilisateurs par sessions:")
                for stat in user_stats:
                    logger.info(f"   User {stat.user_id}: {stat.count} sessions")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du log des statistiques: {e}", exc_info=True)
        finally:
            db.close()
    
    # ============================================================
    # MÉTHODES PUBLIQUES
    # ============================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        Retourne le statut du service de nettoyage.
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        return {
            "is_running": self.is_running,
            "jobs": jobs,
            "config": {
                "session_retention_days": settings.SESSION_RETENTION_DAYS,
                "revoked_session_retention_days": settings.REVOKED_SESSION_RETENTION_DAYS,
            }
        }