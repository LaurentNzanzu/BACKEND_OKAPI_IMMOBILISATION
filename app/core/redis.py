import json
import logging
import time
from typing import Optional, Any
from .config import settings

logger = logging.getLogger(__name__)

# Fallback cache en mémoire
_in_memory_cache = {}

try:
    import redis
    redis_client = redis.Redis.from_url(
        getattr(settings, "REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2
    )
    redis_client.ping()
    REDIS_AVAILABLE = True
    logger.info("✅ Connexion à Redis réussie")
except Exception as e:
    logger.warning("⚠️ Redis non disponible, basculement en cache mémoire: %s", e)
    REDIS_AVAILABLE = False
    redis_client = None


class CacheService:
    @staticmethod
    def get(key: str) -> Optional[Any]:
        if REDIS_AVAILABLE and redis_client:
            try:
                val = redis_client.get(key)
                return json.loads(val) if val else None
            except Exception as e:
                logger.error("Erreur lecture Redis: %s", e)
        
        # Fallback mémoire
        item = _in_memory_cache.get(key)
        if item:
            val, expire_at = item
            if time.time() < expire_at:
                return val
            else:
                _in_memory_cache.pop(key, None)
        return None

    @staticmethod
    def set(key: str, value: Any, ttl: int = 300):
        if REDIS_AVAILABLE and redis_client:
            try:
                redis_client.setex(key, ttl, json.dumps(value))
                return
            except Exception as e:
                logger.error("Erreur écriture Redis: %s", e)
        
        # Fallback mémoire
        _in_memory_cache[key] = (value, time.time() + ttl)

    @staticmethod
    def delete(key: str):
        if REDIS_AVAILABLE and redis_client:
            try:
                redis_client.delete(key)
            except Exception:
                pass
        _in_memory_cache.pop(key, None)

    @staticmethod
    def delete_pattern(pattern: str):
        if REDIS_AVAILABLE and redis_client:
            try:
                keys = redis_client.keys(pattern)
                if keys:
                    redis_client.delete(*keys)
            except Exception:
                pass
        
        # Fallback mémoire (filtrage simple)
        prefix = pattern.replace("*", "")
        keys_to_del = [k for k in _in_memory_cache if k.startswith(prefix)]
        for k in keys_to_del:
            _in_memory_cache.pop(k, None)
