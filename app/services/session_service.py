from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
import logging
import uuid
import hashlib
import time

from ..models.session import SessionUtilisateur
from ..models.utilisateur import Utilisateur
from ..core.config import settings
from ..core.security import get_password_hash, verify_password
from ..core.redis_client import redis_client
from ..services.session_cache_service import SessionCacheService

logger = logging.getLogger(__name__)

# Configuration
MAX_ACTIVE_SESSIONS = getattr(settings, "MAX_ACTIVE_SESSIONS", 5)
SESSION_RETENTION_DAYS = getattr(settings, "SESSION_RETENTION_DAYS", 30)
REVOKED_SESSION_RETENTION_DAYS = getattr(settings, "REVOKED_SESSION_RETENTION_DAYS", 7)


class SessionService:
    """
    Service de gestion des sessions utilisateurs.
    Gère le cycle de vie complet des sessions : création, validation, révocation, etc.
    """

    @staticmethod
    def hash_refresh_token(refresh_token: str) -> str:
        """Hash le refresh token pour le stockage sécurisé en BDD."""
        return get_password_hash(refresh_token)

    @staticmethod
    def verify_refresh_token(plain_token: str, hashed_token: str) -> bool:
        """Vérifie si un refresh token correspond à son hash stocké."""
        return verify_password(plain_token, hashed_token)

    @staticmethod
    def generate_fingerprint(user_agent: str, ip_address: str, additional_data: str = "") -> str:
        """Génère une empreinte unique pour identifier le dispositif/navigateur."""
        data = f"{user_agent}|{ip_address}|{additional_data}".encode('utf-8')
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def create_session(
        db: Session,
        user_id: int,
        refresh_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        fingerprint: Optional[str] = None,
        session_data: Optional[Dict[str, Any]] = None,
        max_active_sessions: int = MAX_ACTIVE_SESSIONS
    ) -> SessionUtilisateur:
        """
        Crée une nouvelle session utilisateur.
        Gère automatiquement la limite de sessions simultanées.
        Écrit en BDD ET en Redis.
        """
        try:
            # 1. Vérifier la limite de sessions actives
            active_sessions = SessionService.get_user_active_sessions(db, user_id)
            active_count = len(active_sessions)

            if active_count >= max_active_sessions:
                logger.warning(
                    f"Limite de sessions atteinte pour l'utilisateur {user_id} "
                    f"({active_count}/{max_active_sessions}) - Révoque la plus ancienne"
                )
                # Révoquer la session la plus ancienne
                oldest_session = active_sessions[-1]
                SessionService.revoke_session(db, oldest_session.session_uuid, user_id)
                db.flush()

            # 2. Hasher le refresh token
            refresh_token_hash = SessionService.hash_refresh_token(refresh_token)

            # 3. Générer le fingerprint si non fourni
            if not fingerprint and user_agent and ip_address:
                fingerprint = SessionService.generate_fingerprint(
                    user_agent, ip_address
                )

            # 4. Préparer les métadonnées de session
            if session_data is None:
                session_data = {}

            session_data.update({
                "created_by": "login",
                "fingerprint_provided": bool(fingerprint),
            })

            # 5. Créer la session en BDD
            session_uuid = str(uuid.uuid4())
            new_session = SessionUtilisateur(
                session_uuid=session_uuid,
                user_id=user_id,
                refresh_token_hash=refresh_token_hash,
                fingerprint=fingerprint,
                user_agent=user_agent,
                ip_address=ip_address,
                date_connexion=datetime.utcnow(),
                date_derniere_activite=datetime.utcnow(),
                est_revoquee=False,
                session_data=session_data
            )

            db.add(new_session)
            db.commit()
            db.refresh(new_session)

            # 6. 🆕 CACHER EN REDIS
            cache_data = {
                "user_id": str(new_session.user_id),
                "revoked": "false",
                "fingerprint": fingerprint or "",
                "user_agent": user_agent or "",
                "ip_address": ip_address or "",
                "session_data": session_data,
                "last_activity": str(time.time()),
            }
            
            cache_success = redis_client.set_session(
                user_id=user_id,
                session_uuid=session_uuid,
                data=cache_data,
                ttl=settings.REDIS_SESSION_TTL
            )
            
            if cache_success:
                logger.debug(f"Session {session_uuid} mise en cache Redis")
            else:
                logger.warning(f"Session {session_uuid} créée en BDD mais non cachée en Redis")

            logger.info(
                f"Nouvelle session créée: {session_uuid} pour l'utilisateur {user_id}"
                f" (IP: {ip_address}, User-Agent: {user_agent})"
            )

            return new_session

        except Exception as e:
            db.rollback()
            logger.error(f"Erreur lors de la création de session: {e}")
            raise

    @staticmethod
    def get_session_by_uuid(
        db: Session, 
        session_uuid: str, 
        user_id: Optional[int] = None
    ) -> Optional[SessionUtilisateur]:
        """
        Récupère une session par son UUID.
        🆕 Priorité: Redis → BDD + recachement.
        """
        # 1. Tenter de récupérer depuis Redis
        if user_id:
            cache_data = redis_client.get_session(user_id, session_uuid)
            if cache_data:
                # Recréer un objet SessionUtilisateur à partir du cache
                # (pour compatibilité avec le code existant)
                try:
                    session = SessionUtilisateur()
                    session.session_uuid = session_uuid
                    session.user_id = int(cache_data.get("user_id", user_id))
                    session.fingerprint = cache_data.get("fingerprint")
                    session.user_agent = cache_data.get("user_agent")
                    session.ip_address = cache_data.get("ip_address")
                    session.est_revoquee = cache_data.get("revoked", False)
                    session.session_data = cache_data.get("session_data", {})
                    session.date_derniere_activite = datetime.fromtimestamp(
                        float(cache_data.get("last_activity", time.time()))
                    )
                    logger.debug(f"Session {session_uuid} récupérée depuis Redis")
                    return session
                except Exception as e:
                    logger.warning(f"Erreur reconstruction session depuis Redis: {e}")

        # 2. Fallback BDD
        query = db.query(SessionUtilisateur).filter(
            SessionUtilisateur.session_uuid == session_uuid
        )
        if user_id is not None:
            query = query.filter(SessionUtilisateur.user_id == user_id)
        
        session = query.first()
        
        # 3. Recachement automatique si trouvé en BDD
        if session and user_id:
            try:
                cache_data = SessionCacheService._session_to_cache_data(session)
                redis_client.set_session(
                    user_id=user_id,
                    session_uuid=session_uuid,
                    data=cache_data,
                    ttl=settings.REDIS_SESSION_TTL
                )
                logger.debug(f"Session {session_uuid} recachée après fallback BDD")
            except Exception as e:
                logger.warning(f"Erreur recachement pour {session_uuid}: {e}")
        
        return session

    @staticmethod
    def get_session_by_refresh_token_hash(
        db: Session, 
        refresh_token_hash: str
    ) -> Optional[SessionUtilisateur]:
        """Récupère une session par le hash de son refresh token."""
        return db.query(SessionUtilisateur).filter(
            SessionUtilisateur.refresh_token_hash == refresh_token_hash
        ).first()

    @staticmethod
    def get_session_by_refresh_token(
        db: Session, 
        refresh_token: str
    ) -> Optional[SessionUtilisateur]:
        """Récupère une session par son refresh token (via hash)."""
        refresh_hash = SessionService.hash_refresh_token(refresh_token)
        return SessionService.get_session_by_refresh_token_hash(db, refresh_hash)

    @staticmethod
    def revoke_session(
        db: Session, 
        session_uuid: str, 
        user_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> bool:
        """
        Révoque une session.
        🆕 Marque en BDD ET en Redis.
        """
        session = SessionService.get_session_by_uuid(db, session_uuid, user_id)
        if not session:
            logger.warning(f"Session {session_uuid} introuvable pour révocation")
            return False

        if session.est_revoquee:
            logger.info(f"Session {session_uuid} déjà révoquée")
            return True

        # Marquer comme révoquée en BDD
        session.revoke()
        
        # Ajouter la raison dans les métadonnées
        if reason:
            if not session.session_data:
                session.session_data = {}
            session.session_data["revocation_reason"] = reason
            session.session_data["revoked_at"] = datetime.utcnow().isoformat()

        db.commit()

        # 🆕 Marquer comme révoquée en Redis
        try:
            redis_client.revoke_session(session.user_id, session_uuid)
            logger.debug(f"Session {session_uuid} révoquée en Redis")
        except Exception as e:
            logger.warning(f"Erreur révocation Redis pour {session_uuid}: {e}")

        logger.warning(
            f"Session {session_uuid} révoquée pour l'utilisateur {session.user_id}"
            f" (Raison: {reason or 'Non spécifiée'})"
        )
        return True

    @staticmethod
    def revoke_oldest_session(db: Session, user_id: int) -> Optional[SessionUtilisateur]:
        """Révoque la session active la plus ancienne d'un utilisateur."""
        sessions = SessionService.get_user_active_sessions(db, user_id)
        if not sessions:
            return None
        
        oldest_session = sessions[-1]
        SessionService.revoke_session(
            db, 
            oldest_session.session_uuid, 
            user_id,
            reason="Limite de sessions atteinte - rotation automatique"
        )
        return oldest_session

    @staticmethod
    def get_user_active_sessions(
        db: Session, 
        user_id: int,
        limit: Optional[int] = None
    ) -> List[SessionUtilisateur]:
        """Récupère toutes les sessions actives d'un utilisateur."""
        query = db.query(SessionUtilisateur).filter(
            and_(
                SessionUtilisateur.user_id == user_id,
                SessionUtilisateur.est_revoquee == False
            )
        ).order_by(desc(SessionUtilisateur.date_connexion))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()

    @staticmethod
    def get_user_all_sessions(
        db: Session, 
        user_id: int,
        limit: Optional[int] = None
    ) -> List[SessionUtilisateur]:
        """Récupère toutes les sessions (actives + révoquées) d'un utilisateur."""
        query = db.query(SessionUtilisateur).filter(
            SessionUtilisateur.user_id == user_id
        ).order_by(desc(SessionUtilisateur.date_connexion))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()

    @staticmethod
    def update_session_activity(
        db: Session, 
        session_uuid: str,
        update_interval: int = 60
    ) -> bool:
        """Met à jour la date de dernière activité de la session."""
        session = SessionService.get_session_by_uuid(db, session_uuid)
        if not session or session.est_revoquee:
            return False

        # Vérifier si la mise à jour est nécessaire (optimisation)
        if session.date_derniere_activite:
            time_diff = (datetime.utcnow() - session.date_derniere_activite).total_seconds()
            if time_diff < update_interval:
                return True

        session.update_activity()
        db.commit()
        
        # 🆕 Mettre à jour en Redis (optionnel)
        try:
            if session.user_id:
                key = f"session:{session.user_id}:{session_uuid}"
                redis_client._client.hset(key, "last_activity", str(time.time()))
        except Exception:
            pass
        
        return True

    @staticmethod
    def validate_session(
        db: Session, 
        session_uuid: str,
        refresh_token: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> bool:
        """Valide qu'une session existe et est active."""
        session = SessionService.get_session_by_uuid(db, session_uuid, user_id)
        if not session:
            logger.warning(f"Session {session_uuid} introuvable")
            return False

        if session.est_revoquee:
            logger.warning(f"Session {session_uuid} révoquée")
            return False

        # Vérifier le refresh token si fourni
        if refresh_token:
            if not SessionService.verify_refresh_token(
                refresh_token, 
                session.refresh_token_hash
            ):
                logger.warning(f"Refresh token invalide pour la session {session_uuid}")
                return False

        return True

    @staticmethod
    def rotate_session(
        db: Session, 
        session_uuid: str,
        new_refresh_token: str,
        user_id: Optional[int] = None
    ) -> bool:
        """Effectue la rotation du refresh token pour une session."""
        session = SessionService.get_session_by_uuid(db, session_uuid, user_id)
        if not session:
            return False

        if session.est_revoquee:
            logger.warning(f"Tentative de rotation sur session révoquée {session_uuid}")
            return False

        # Mettre à jour le hash du refresh token
        new_hash = SessionService.hash_refresh_token(new_refresh_token)
        session.refresh_token_hash = new_hash
        session.update_activity()
        
        # Ajouter l'historique de rotation
        if not session.session_data:
            session.session_data = {}
        if "rotation_history" not in session.session_data:
            session.session_data["rotation_history"] = []
        
        session.session_data["rotation_history"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "rotation_number": len(session.session_data.get("rotation_history", [])) + 1
        })

        db.commit()
        
        # 🆕 Mettre à jour le cache
        try:
            cache_data = SessionCacheService._session_to_cache_data(session)
            redis_client.set_session(
                user_id=session.user_id,
                session_uuid=session_uuid,
                data=cache_data,
                ttl=settings.REDIS_SESSION_TTL
            )
        except Exception as e:
            logger.warning(f"Erreur mise à jour cache après rotation: {e}")

        logger.info(f"Rotation de session {session_uuid} effectuée")
        return True

    @staticmethod
    def revoke_all_sessions(db: Session, user_id: int, exclude_uuid: Optional[str] = None) -> int:
        """Révoque toutes les sessions d'un utilisateur."""
        sessions = SessionService.get_user_active_sessions(db, user_id)
        revoked_count = 0
        
        for session in sessions:
            if exclude_uuid and session.session_uuid == exclude_uuid:
                continue
            SessionService.revoke_session(
                db, 
                session.session_uuid, 
                user_id,
                reason="Révocation massive par administrateur"
            )
            revoked_count += 1
        
        # 🆕 Révoquer en Redis
        try:
            redis_client.revoke_all_user_sessions(user_id)
        except Exception as e:
            logger.warning(f"Erreur révocation massive Redis: {e}")
        
        return revoked_count

    @staticmethod
    def get_session_stats(db: Session) -> Dict[str, Any]:
        """Retourne des statistiques sur les sessions."""
        total_sessions = db.query(SessionUtilisateur).count()
        active_sessions = db.query(SessionUtilisateur).filter(
            SessionUtilisateur.est_revoquee == False
        ).count()
        revoked_sessions = total_sessions - active_sessions

        # Sessions par utilisateur (top 10)
        user_stats = db.query(
            SessionUtilisateur.user_id,
            func.count(SessionUtilisateur.id).label('session_count')
        ).group_by(SessionUtilisateur.user_id).order_by(
            func.count(SessionUtilisateur.id).desc()
        ).limit(10).all()

        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "revoked_sessions": revoked_sessions,
            "active_percentage": round(
                (active_sessions / total_sessions * 100) if total_sessions > 0 else 0, 
                2
            ),
            "user_stats": [
                {"user_id": stat.user_id, "session_count": stat.session_count}
                for stat in user_stats
            ]
        }

    @staticmethod
    def cleanup_old_sessions(
        db: Session,
        active_retention_days: int = SESSION_RETENTION_DAYS,
        revoked_retention_days: int = REVOKED_SESSION_RETENTION_DAYS
    ) -> int:
        """Nettoie les sessions anciennes."""
        cutoff_active = datetime.utcnow() - timedelta(days=active_retention_days)
        cutoff_revoked = datetime.utcnow() - timedelta(days=revoked_retention_days)

        # Supprimer les sessions actives inactives
        active_deleted = db.query(SessionUtilisateur).filter(
            and_(
                SessionUtilisateur.est_revoquee == False,
                SessionUtilisateur.date_derniere_activite < cutoff_active
            )
        ).delete(synchronize_session=False)

        # Supprimer les sessions révoquées anciennes
        revoked_deleted = db.query(SessionUtilisateur).filter(
            and_(
                SessionUtilisateur.est_revoquee == True,
                SessionUtilisateur.date_fin < cutoff_revoked
            )
        ).delete(synchronize_session=False)

        total_deleted = active_deleted + revoked_deleted
        if total_deleted > 0:
            db.commit()
            logger.info(f"Cleanup: {total_deleted} sessions supprimées "
                       f"({active_deleted} inactives, {revoked_deleted} révoquées)")

        return total_deleted