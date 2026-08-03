from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import time

from ...core.redis_client import redis_client
from ...core.config import settings
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/redis/health")
async def redis_health():
    """
    Vérifie la santé de Redis.
    """
    is_healthy = redis_client.is_healthy()
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "timestamp": time.time(),
        "redis_host": settings.REDIS_HOST,
        "redis_port": settings.REDIS_PORT,
    }


@router.get("/redis/stats")
async def redis_stats(
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Récupère les statistiques de Redis.
    Nécessite des droits administrateur.
    """
    if not current_user.role or current_user.role.nom.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits administrateur requis"
        )
    
    stats = redis_client.get_stats()
    return stats


@router.get("/cache/hit-rate")
async def cache_hit_rate():
    """
    Calcule le taux de succès du cache.
    (À implémenter avec des métriques plus avancées)
    """
    # TODO: Implémenter avec des métriques de performance
    return {
        "hit_rate": 0.95,  # Valeur estimée
        "message": "Implémentation à venir avec des métriques avancées"
    }