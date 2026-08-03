import json
import logging
import asyncio
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from ..core.redis_client import redis_client
from ..core.config import settings
from ..models.session import SessionUtilisateur

logger = logging.getLogger(__name__)


class SessionCacheService:
    """
    Service de cache des sessions utilisateurs.
    Gère la lecture/écriture en Redis avec fallback BDD.
    """

    # ============================================================
    # MÉTHODES PRIVÉES
    # ============================================================

    @staticmethod
    def _session_to_cache_data(session: SessionUtilisateur) -> Dict[str, Any]:
        """
        Convertit un objet SessionUtilisateur en données de cache Redis.

        Args:
            session: Objet SessionUtilisateur

        Returns:
            Dict[str, Any]: Données formatées pour Redis
        """
        return {
            "user_id": str(session.user_id),
            "revoked": str(session.est_revoquee).lower(),
            "fingerprint": session.fingerprint or "",
            "user_agent": session.user_agent or "",
            "ip_address": session.ip_address or "",
            "session_data": json.dumps(session.session_data or {}),
            "last_activity": str(session.date_derniere_activite.timestamp())
            if session.date_derniere_activite
            else str(time.time()),
        }

    @staticmethod
    async def _async_cache_session(
        user_id: int,
        session_uuid: str,
        cache_data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """
        Cache asynchrone d'une session en Redis.

        Args:
            user_id: ID de l'utilisateur
            session_uuid: UUID de la session
            cache_data: Données à cacher
            ttl: Durée de vie en secondes (optionnel)
        """
        try:
            result = redis_client.set_session(
                user_id=user_id,
                session_uuid=session_uuid,
                data=cache_data,
                ttl=ttl,
            )
            if result:
                logger.debug(f"Session {session_uuid} recachée en arrière-plan")
        except Exception as e:
            logger.error(f"Erreur cache asynchrone pour {session_uuid}: {e}")

    # ============================================================
    # MÉTHODES PUBLIQUES
    # ============================================================

    @staticmethod
    def cache_session(
        db: Session,
        user_id: int,
        session_uuid: str,
        session_data: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Cache une session en Redis.
        Si Redis est indisponible, retourne False (ne pas bloquer).

        Args:
            db: Session SQLAlchemy
            user_id: ID de l'utilisateur
            session_uuid: UUID de la session
            session_data: Données de session (optionnel)
            ttl: Durée de vie en secondes (optionnel)

        Returns:
            bool: True si le cache a réussi, False sinon
        """
        try:
            # Import local pour éviter l'importation circulaire
            from ..services.session_service import SessionService

            # Si les données ne sont pas fournies, récupérer depuis la BDD
            if session_data is None:
                session = SessionService.get_session_by_uuid(db, session_uuid)
                if not session:
                    logger.warning(f"Session {session_uuid} introuvable pour le cache")
                    return False
                session_data = SessionCacheService._session_to_cache_data(session)

            # Écrire en Redis
            result = redis_client.set_session(
                user_id=user_id,
                session_uuid=session_uuid,
                data=session_data,
                ttl=ttl,
            )

            if result:
                logger.debug(f"Session {session_uuid} mise en cache Redis")
            else:
                logger.warning(f"Échec de cache pour la session {session_uuid}")

            return result

        except Exception as e:
            logger.error(f"Erreur lors du cache de la session {session_uuid}: {e}")
            return False

    @staticmethod
    def get_session_data(
        db: Session,
        user_id: int,
        session_uuid: str,
        check_revoked: bool = True,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Récupère les données d'une session.
        Priorité: Redis → BDD + recachement.

        Args:
            db: Session SQLAlchemy
            user_id: ID de l'utilisateur
            session_uuid: UUID de la session
            check_revoked: Vérifier si la session est révoquée

        Returns:
            Tuple[Optional[Dict[str, Any]], bool]: (session_data, from_cache)
        """
        # 1. TENTER LA LECTURE REDIS
        try:
            cache_data = redis_client.get_session(user_id, session_uuid)
            if cache_data:
                # Vérifier si la session est révoquée
                if check_revoked and cache_data.get("revoked", False):
                    logger.debug(f"Session {session_uuid} révoquée en cache")
                    return None, True

                logger.debug(f"Session {session_uuid} trouvée en cache Redis")
                return cache_data, True
        except Exception as e:
            logger.warning(f"Erreur lecture Redis pour {session_uuid}: {e}")

        # 2. FALLBACK BDD
        try:
            # Import local pour éviter l'importation circulaire
            from ..services.session_service import SessionService

            session = SessionService.get_session_by_uuid(db, session_uuid, user_id)
            if not session:
                logger.warning(f"Session {session_uuid} introuvable en BDD")
                return None, False

            # Vérifier si révoquée
            if check_revoked and session.est_revoquee:
                logger.debug(f"Session {session_uuid} révoquée en BDD")
                return None, False

            # 3. RECACHEMENT AUTOMATIQUE
            cache_data = SessionCacheService._session_to_cache_data(session)
            asyncio.create_task(
                SessionCacheService._async_cache_session(
                    user_id, session_uuid, cache_data
                )
            )

            logger.info(f"Session {session_uuid} recachée après fallback BDD")
            return cache_data, False

        except Exception as e:
            logger.error(f"Erreur fallback BDD pour {session_uuid}: {e}")
            return None, False

    @staticmethod
    def validate_session(
        db: Session,
        user_id: int,
        session_uuid: str,
        fingerprint: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Valide une session avec vérification en cache.

        Args:
            db: Session SQLAlchemy
            user_id: ID de l'utilisateur
            session_uuid: UUID de la session
            fingerprint: Empreinte du navigateur (optionnel)

        Returns:
            Tuple[bool, str]: (is_valid, message)
        """
        # 1. Récupérer les données de la session
        session_data, from_cache = SessionCacheService.get_session_data(
            db, user_id, session_uuid, check_revoked=True
        )

        if not session_data:
            return False, "Session invalide ou révoquée"

        # 2. Vérifier si révoquée (double vérification)
        if session_data.get("revoked", False):
            return False, "Session révoquée"

        # 3. Vérifier le fingerprint (si fourni)
        if fingerprint:
            stored_fingerprint = session_data.get("fingerprint")
            if stored_fingerprint and stored_fingerprint != fingerprint:
                # Détection de compromission - révoquer toutes les sessions
                logger.warning(
                    f"⚠️ Compromission détectée pour l'utilisateur {user_id} "
                    f"(Fingerprint mismatch: {stored_fingerprint[:10]}... vs {fingerprint[:10]}...)"
                )

                # Révoquer toutes les sessions en BDD et Redis
                try:
                    # Import local pour éviter l'importation circulaire
                    from ..services.session_service import SessionService

                    # BDD
                    SessionService.revoke_all_sessions(db, user_id)
                    # Redis
                    redis_client.revoke_all_user_sessions(user_id)
                except Exception as e:
                    logger.error(f"Erreur lors de la révocation des sessions: {e}")

                return False, "Session compromise détectée"

        # 4. Mettre à jour l'activité (asynchrone si possible)
        try:
            SessionCacheService.update_activity_async(db, user_id, session_uuid)
        except Exception as e:
            logger.debug(f"Erreur mise à jour activité: {e}")

        return True, "Session valide"

    @staticmethod
    def is_session_active(
        db: Session,
        user_id: int,
        session_uuid: str,
    ) -> bool:
        """
        Vérifie si une session est active (existe et non révoquée).

        Args:
            db: Session SQLAlchemy
            user_id: ID de l'utilisateur
            session_uuid: UUID de la session

        Returns:
            bool: True si active, False sinon
        """
        # 1. Vérifier en Redis
        try:
            cache_data = redis_client.get_session(user_id, session_uuid)
            if cache_data:
                return not cache_data.get("revoked", False)
        except Exception:
            pass

        # 2. Fallback BDD
        try:
            # Import local pour éviter l'importation circulaire
            from ..services.session_service import SessionService

            session = SessionService.get_session_by_uuid(db, session_uuid, user_id)
            if session:
                return not session.est_revoquee
        except Exception:
            pass

        return False

    @staticmethod
    def revoke_session_cache(user_id: int, session_uuid: str) -> bool:
        """
        Marque une session comme révoquée en cache Redis.

        Args:
            user_id: ID de l'utilisateur
            session_uuid: UUID de la session

        Returns:
            bool: True si la révocation a réussi
        """
        try:
            return redis_client.revoke_session(user_id, session_uuid)
        except Exception as e:
            logger.error(f"Erreur révocation cache pour {session_uuid}: {e}")
            return False

    @staticmethod
    def delete_session_cache(user_id: int, session_uuid: str) -> bool:
        """
        Supprime une session du cache Redis.

        Args:
            user_id: ID de l'utilisateur
            session_uuid: UUID de la session

        Returns:
            bool: True si la suppression a réussi
        """
        try:
            return redis_client.delete_session(user_id, session_uuid)
        except Exception as e:
            logger.error(f"Erreur suppression cache pour {session_uuid}: {e}")
            return False

    @staticmethod
    def revoke_all_user_sessions_cache(user_id: int) -> int:
        """
        Révoque toutes les sessions d'un utilisateur en Redis.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            int: Nombre de sessions révoquées
        """
        try:
            return redis_client.revoke_all_user_sessions(user_id)
        except Exception as e:
            logger.error(f"Erreur révocation massive cache pour user {user_id}: {e}")
            return 0

    @staticmethod
    def update_activity_async(db: Session, user_id: int, session_uuid: str) -> None:
        """
        Met à jour l'activité d'une session de manière asynchrone.

        Args:
            db: Session SQLAlchemy
            user_id: ID de l'utilisateur
            session_uuid: UUID de la session
        """
        try:
            # Import local pour éviter l'importation circulaire
            from ..services.session_service import SessionService

            # Mettre à jour en BDD
            SessionService.update_session_activity(db, session_uuid)

            # Mettre à jour en Redis (optionnel)
            key = f"session:{user_id}:{session_uuid}"
            redis_client._client.hset(key, "last_activity", str(time.time()))

        except Exception as e:
            logger.debug(f"Erreur mise à jour activité asynchrone: {e}")

    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """
        Récupère les statistiques du cache Redis.

        Returns:
            Dict[str, Any]: Statistiques du cache
        """
        return redis_client.get_stats()

    @staticmethod
    def is_redis_available() -> bool:
        """
        Vérifie si Redis est disponible.

        Returns:
            bool: True si Redis est disponible
        """
        return redis_client.is_healthy()