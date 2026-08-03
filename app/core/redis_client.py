import json
import logging
import time
from typing import Optional, Dict, Any, List
from functools import wraps
import redis
from redis import Redis
from redis.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from .config import settings

logger = logging.getLogger(__name__)

# === DECORATOR FOR ERROR HANDLING ===

def handle_redis_errors(default_return=None):
    """
    Décorateur pour gérer les erreurs Redis de manière uniforme.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (ConnectionError, TimeoutError) as e:
                logger.warning(f"Redis connection error in {func.__name__}: {e}")
                return default_return
            except RedisError as e:
                logger.error(f"Redis error in {func.__name__}: {e}")
                return default_return
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                return default_return
        return wrapper
    return decorator


class RedisClient:
    """
    Client Redis avec gestion des erreurs, pool de connexions et fallback.
    Gère les sessions et la blacklist des tokens.
    """
    
    _instance = None
    _client = None
    _connection_pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._initialize()
    
    def _initialize(self):
        """Initialise la connexion Redis avec pool de connexions."""
        try:
            # Créer le pool de connexions
            self._connection_pool = ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD or None,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                retry_on_timeout=settings.REDIS_RETRY_ON_TIMEOUT,
                decode_responses=True,
            )
            
            # Créer le client
            self._client = Redis(connection_pool=self._connection_pool)
            
            # Tester la connexion
            self._client.ping()
            logger.info(f"✅ Redis connecté avec succès à {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            
        except Exception as e:
            logger.error(f"❌ Échec de connexion à Redis: {e}")
            self._client = None
            self._connection_pool = None
    
    def _get_client(self) -> Optional[Redis]:
        """Retourne le client Redis ou None si indisponible."""
        if self._client is None:
            # Tentative de reconnexion
            try:
                self._initialize()
            except Exception:
                pass
        return self._client
    
    def is_healthy(self) -> bool:
        """
        Vérifie si Redis est disponible.
        """
        client = self._get_client()
        if client is None:
            return False
        try:
            client.ping()
            return True
        except Exception:
            return False
    
    # ============================================================
    # MÉTHODES DE SESSIONS (Phase 3)
    # ============================================================
    
    @handle_redis_errors(default_return=None)
    def get_session(self, user_id: int, session_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Récupère une session depuis Redis.
        Clé: session:{user_id}:{session_uuid}
        """
        client = self._get_client()
        if client is None:
            return None
        
        key = f"session:{user_id}:{session_uuid}"
        data = client.hgetall(key)
        
        if not data:
            return None
        
        # Convertir les données
        return {
            "user_id": data.get("user_id"),
            "revoked": data.get("revoked", "false") == "true",
            "fingerprint": data.get("fingerprint"),
            "user_agent": data.get("user_agent"),
            "ip_address": data.get("ip_address"),
            "session_data": json.loads(data.get("session_data", "{}")) if data.get("session_data") else {},
            "last_activity": data.get("last_activity"),
        }
    
    @handle_redis_errors(default_return=False)
    def set_session(
        self, 
        user_id: int, 
        session_uuid: str, 
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Stocke une session en Redis avec TTL.
        """
        client = self._get_client()
        if client is None:
            return False
        
        key = f"session:{user_id}:{session_uuid}"
        ttl = ttl or settings.REDIS_SESSION_TTL
        
        # Préparer les données
        session_data = {
            "user_id": str(data.get("user_id", user_id)),
            "revoked": str(data.get("revoked", False)).lower(),
            "fingerprint": data.get("fingerprint", ""),
            "user_agent": data.get("user_agent", ""),
            "ip_address": data.get("ip_address", ""),
            "session_data": json.dumps(data.get("session_data", {})),
            "last_activity": data.get("last_activity", str(time.time())),
        }
        
        # Utiliser un pipeline pour atomicité
        pipe = client.pipeline()
        pipe.hset(key, mapping=session_data)
        pipe.expire(key, ttl)
        pipe.execute()
        
        logger.debug(f"Session {session_uuid} mise en cache Redis (TTL: {ttl}s)")
        return True
    
    @handle_redis_errors(default_return=False)
    def revoke_session(self, user_id: int, session_uuid: str) -> bool:
        """
        Marque une session comme révoquée en Redis.
        """
        client = self._get_client()
        if client is None:
            return False
        
        key = f"session:{user_id}:{session_uuid}"
        client.hset(key, "revoked", "true")
        client.hset(key, "revoked_at", str(time.time()))
        
        logger.info(f"Session {session_uuid} marquée comme révoquée en Redis")
        return True
    
    @handle_redis_errors(default_return=False)
    def delete_session(self, user_id: int, session_uuid: str) -> bool:
        """
        Supprime une session de Redis.
        """
        client = self._get_client()
        if client is None:
            return False
        
        key = f"session:{user_id}:{session_uuid}"
        deleted = client.delete(key)
        
        if deleted:
            logger.debug(f"Session {session_uuid} supprimée de Redis")
        return bool(deleted)
    
    @handle_redis_errors(default_return=None)
    def get_ttl(self, user_id: int, session_uuid: str) -> Optional[int]:
        """
        Récupère le TTL restant d'une session en Redis.
        """
        client = self._get_client()
        if client is None:
            return None
        
        key = f"session:{user_id}:{session_uuid}"
        return client.ttl(key)
    
    @handle_redis_errors(default_return=0)
    def get_session_count(self, user_id: Optional[int] = None) -> int:
        """
        Compte le nombre de sessions en cache.
        Option: filtrer par user_id.
        """
        client = self._get_client()
        if client is None:
            return 0
        
        pattern = f"session:{user_id}:*" if user_id else "session:*"
        keys = client.keys(pattern)
        return len(keys)
    
    @handle_redis_errors(default_return=[])
    def get_user_sessions_keys(self, user_id: int) -> List[str]:
        """
        Récupère toutes les clés de sessions d'un utilisateur.
        """
        client = self._get_client()
        if client is None:
            return []
        
        pattern = f"session:{user_id}:*"
        return client.keys(pattern)
    
    @handle_redis_errors(default_return=False)
    def revoke_all_user_sessions(self, user_id: int) -> int:
        """
        Révoque toutes les sessions d'un utilisateur en Redis.
        """
        client = self._get_client()
        if client is None:
            return 0
        
        keys = self.get_user_sessions_keys(user_id)
        count = 0
        for key in keys:
            client.hset(key, "revoked", "true")
            client.hset(key, "revoked_at", str(time.time()))
            count += 1
        
        logger.info(f"{count} sessions révoquées pour l'utilisateur {user_id} en Redis")
        return count
    
    @handle_redis_errors(default_return=False)
    def delete_all_user_sessions(self, user_id: int) -> int:
        """
        Supprime toutes les sessions d'un utilisateur de Redis.
        """
        client = self._get_client()
        if client is None:
            return 0
        
        keys = self.get_user_sessions_keys(user_id)
        if keys:
            deleted = client.delete(*keys)
            logger.info(f"{deleted} sessions supprimées pour l'utilisateur {user_id} en Redis")
            return deleted
        return 0
    
    # ============================================================
    # 🔴 NOUVEAU : MÉTHODES DE BLACKLIST (Phase 4)
    # ============================================================
    
    @handle_redis_errors(default_return=False)
    def add_to_blacklist(self, jti: str, ttl: int) -> bool:
        """
        Ajoute un JTI à la blacklist.
        Clé: blacklist:{jti} -> "revoked"
        TTL: temps restant avant expiration du token
        
        Args:
            jti: JWT ID du token à blacklister
            ttl: Durée de vie en secondes (temps restant avant expiration)
        
        Returns:
            bool: True si ajout réussi, False sinon
        """
        if not jti:
            logger.warning("Tentative d'ajout à la blacklist avec un JTI vide")
            return False
        
        if ttl <= 0:
            logger.debug(f"JTI {jti} déjà expiré, pas besoin de blacklister")
            return True
        
        client = self._get_client()
        if client is None:
            return False
        
        key = f"blacklist:{jti}"
        client.setex(key, ttl, "revoked")
        
        logger.info(f"JTI {jti} ajouté à la blacklist (TTL: {ttl}s)")
        return True
    
    @handle_redis_errors(default_return=False)
    def is_blacklisted(self, jti: str) -> bool:
        """
        Vérifie si un JTI est dans la blacklist.
        
        Args:
            jti: JWT ID à vérifier
        
        Returns:
            bool: True si blacklisté, False sinon
        """
        if not jti:
            logger.warning("Vérification de blacklist avec un JTI vide")
            return False
        
        client = self._get_client()
        if client is None:
            # Si Redis est down, on considère que le token n'est pas blacklisté
            # (fallback de sécurité pour ne pas bloquer tous les tokens)
            logger.warning("Redis indisponible, vérification blacklist ignorée")
            return False
        
        key = f"blacklist:{jti}"
        exists = client.exists(key)
        
        if exists:
            # Récupérer le TTL restant pour logging
            ttl = client.ttl(key)
            logger.debug(f"JTI {jti} blacklisté (TTL restant: {ttl}s)")
        else:
            logger.debug(f"JTI {jti} non blacklisté")
        
        return bool(exists)
    
    @handle_redis_errors(default_return=False)
    def remove_from_blacklist(self, jti: str) -> bool:
        """
        Supprime un JTI de la blacklist (cas exceptionnel).
        
        Args:
            jti: JWT ID à supprimer de la blacklist
        
        Returns:
            bool: True si suppression réussie, False sinon
        """
        if not jti:
            return False
        
        client = self._get_client()
        if client is None:
            return False
        
        key = f"blacklist:{jti}"
        deleted = client.delete(key)
        
        if deleted:
            logger.info(f"JTI {jti} supprimé de la blacklist")
        else:
            logger.warning(f"JTI {jti} non trouvé dans la blacklist")
        
        return bool(deleted)
    
    @handle_redis_errors(default_return=-1)
    def get_blacklist_ttl(self, jti: str) -> int:
        """
        Récupère le TTL restant d'un JTI dans la blacklist.
        
        Args:
            jti: JWT ID
        
        Returns:
            int: TTL restant en secondes, -1 si non trouvé
        """
        if not jti:
            return -1
        
        client = self._get_client()
        if client is None:
            return -1
        
        key = f"blacklist:{jti}"
        return client.ttl(key)
    
    @handle_redis_errors(default_return=0)
    def bulk_add_to_blacklist(self, jtis: List[str], ttl: int) -> int:
        """
        Ajoute plusieurs JTI à la blacklist en une seule opération (pipeline).
        
        Args:
            jtis: Liste des JTI à blacklister
            ttl: Durée de vie en secondes
        
        Returns:
            int: Nombre de JTI ajoutés avec succès
        """
        if not jtis:
            return 0
        
        if ttl <= 0:
            logger.debug("TTL <= 0, aucun token à blacklister")
            return 0
        
        client = self._get_client()
        if client is None:
            return 0
        
        try:
            pipe = client.pipeline()
            count = 0
            for jti in jtis:
                if jti:
                    key = f"blacklist:{jti}"
                    pipe.setex(key, ttl, "revoked")
                    count += 1
            
            if count > 0:
                pipe.execute()
                logger.info(f"{count} JTI ajoutés à la blacklist en bulk (TTL: {ttl}s)")
            
            return count
            
        except Exception as e:
            logger.error(f"Erreur lors du bulk add à la blacklist: {e}")
            return 0
    
    @handle_redis_errors(default_return={})
    def get_blacklist_stats(self) -> Dict[str, Any]:
        """
        Récupère des statistiques sur la blacklist.
        
        Returns:
            Dict: Statistiques de la blacklist
        """
        client = self._get_client()
        if client is None:
            return {"available": False, "error": "Redis indisponible"}
        
        # Récupérer toutes les clés de la blacklist
        keys = client.keys("blacklist:*")
        
        total_blacklisted = len(keys)
        ttl_values = []
        
        for key in keys:
            ttl = client.ttl(key)
            if ttl > 0:
                ttl_values.append(ttl)
        
        # Statistiques
        stats = {
            "available": True,
            "total_blacklisted": total_blacklisted,
            "avg_ttl": sum(ttl_values) / len(ttl_values) if ttl_values else 0,
            "min_ttl": min(ttl_values) if ttl_values else 0,
            "max_ttl": max(ttl_values) if ttl_values else 0,
            "ttl_distribution": {
                "0-60s": len([t for t in ttl_values if 0 < t <= 60]),
                "1-5min": len([t for t in ttl_values if 60 < t <= 300]),
                "5-10min": len([t for t in ttl_values if 300 < t <= 600]),
                "10-15min": len([t for t in ttl_values if 600 < t <= 900]),
                ">15min": len([t for t in ttl_values if 900 < t]),
            }
        }
        
        return stats
    
    @handle_redis_errors(default_return=0)
    def cleanup_blacklist(self) -> int:
        """
        Nettoie les entrées expirées de la blacklist.
        (Redis le fait automatiquement, cette méthode est pour le monitoring)
        
        Returns:
            int: Nombre d'entrées supprimées (toujours 0 car Redis gère automatiquement)
        """
        # Redis gère automatiquement les expirations
        # Cette méthode est juste pour le logging/monitoring
        logger.info("Redis gère automatiquement le nettoyage de la blacklist via TTL")
        return 0
    
    @handle_redis_errors(default_return={})
    def get_stats(self) -> Dict[str, Any]:
        """
        Récupère des statistiques sur Redis (sessions + blacklist).
        """
        client = self._get_client()
        if client is None:
            return {"available": False}
        
        info = client.info()
        
        # Statistiques des sessions
        session_keys = client.keys("session:*")
        active_sessions = 0
        revoked_sessions = 0
        
        for key in session_keys:
            revoked = client.hget(key, "revoked")
            if revoked == "true":
                revoked_sessions += 1
            else:
                active_sessions += 1
        
        # Statistiques de la blacklist
        blacklist_keys = client.keys("blacklist:*")
        
        return {
            "available": True,
            "redis_version": info.get("redis_version"),
            "used_memory": info.get("used_memory_human"),
            "uptime_seconds": info.get("uptime_in_seconds"),
            "connected_clients": info.get("connected_clients"),
            "sessions": {
                "total": len(session_keys),
                "active": active_sessions,
                "revoked": revoked_sessions,
            },
            "blacklist": {
                "total": len(blacklist_keys),
                "entries": len(blacklist_keys),
            }
        }


# Instance unique du client Redis
redis_client = RedisClient()