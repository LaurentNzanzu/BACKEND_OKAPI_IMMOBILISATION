import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...core.redis_client import redis_client
from ...models.utilisateur import Utilisateur
from ...services.session_service import SessionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/blacklist", tags=["Admin - Blacklist"])


# === VÉRIFICATION ADMIN ===

def require_admin(current_user: Utilisateur = Depends(get_current_user)):
    """
    Vérifie que l'utilisateur a les droits administrateur.
    """
    if not current_user.role or current_user.role.nom.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits administrateur requis"
        )
    return current_user


# === ROUTES ===

@router.post("/token")
async def add_token_to_blacklist(
    jti: str = Query(..., description="JWT ID du token à blacklister"),
    ttl: Optional[int] = Query(None, description="TTL en secondes (défaut: 900 = 15 min)"),
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Ajoute un token spécifique à la blacklist.
    Nécessite des droits administrateur.
    """
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JTI requis"
        )
    
    # TTL par défaut : 15 minutes
    if ttl is None:
        ttl = 900  # 15 min
    
    if ttl <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTL doit être supérieur à 0"
        )
    
    # Ajouter à la blacklist
    success = redis_client.add_to_blacklist(jti, ttl)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'ajout à la blacklist"
        )
    
    logger.info(f"Admin {admin.id} a ajouté le JTI {jti} à la blacklist (TTL: {ttl}s)")
    
    return {
        "message": f"Token {jti} ajouté à la blacklist",
        "jti": jti,
        "ttl": ttl,
        "admin_id": admin.id
    }


@router.post("/user/{user_id}")
async def blacklist_all_user_tokens(
    user_id: int,
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Blackliste tous les tokens d'un utilisateur.
    Nécessite des droits administrateur.
    """
    # Vérifier que l'utilisateur existe
    user = db.query(Utilisateur).filter(Utilisateur.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur introuvable"
        )
    
    # Récupérer toutes les sessions actives de l'utilisateur
    active_sessions = SessionService.get_user_active_sessions(db, user_id)
    
    # Extraire les JTI des access tokens (stockés dans session_data)
    jtis = []
    for session in active_sessions:
        if session.session_data and "access_jti" in session.session_data:
            jtis.append(session.session_data["access_jti"])
    
    if not jtis:
        return {
            "message": f"Aucun token actif trouvé pour l'utilisateur {user.email}",
            "user_id": user_id,
            "tokens_blacklisted": 0
        }
    
    # Ajouter tous les JTI à la blacklist
    ttl = 900  # 15 minutes
    count = redis_client.bulk_add_to_blacklist(jtis, ttl)
    
    # Révoquer toutes les sessions en BDD et Redis
    revoked_count = SessionService.revoke_all_sessions(db, user_id)
    
    logger.info(
        f"Admin {admin.id} a blacklisté {count} tokens de l'utilisateur {user.email} "
        f"({revoked_count} sessions révoquées)"
    )
    
    return {
        "message": f"{count} tokens de l'utilisateur {user.email} blacklistés",
        "user_id": user_id,
        "user_email": user.email,
        "tokens_blacklisted": count,
        "sessions_revoked": revoked_count
    }


@router.get("/stats")
async def get_blacklist_stats(
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Récupère des statistiques sur la blacklist.
    Nécessite des droits administrateur.
    """
    stats = redis_client.get_blacklist_stats()
    
    # Ajouter des statistiques BDD
    total_users = db.query(Utilisateur).count()
    total_sessions = db.query(SessionUtilisateur).count()
    
    return {
        **stats,
        "database_stats": {
            "total_users": total_users,
            "total_sessions": total_sessions,
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@router.delete("/{jti}")
async def remove_from_blacklist(
    jti: str,
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Supprime un JTI de la blacklist (cas exceptionnel).
    Nécessite des droits SUPER_ADMIN.
    """
    # Vérifier que l'admin a les droits SUPER_ADMIN
    if not admin.role or admin.role.nom.upper() not in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Droits SUPER_ADMIN requis pour cette opération"
        )
    
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JTI requis"
        )
    
    # Supprimer de la blacklist
    success = redis_client.remove_from_blacklist(jti)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="JTI non trouvé dans la blacklist"
        )
    
    logger.info(f"Admin {admin.id} a supprimé le JTI {jti} de la blacklist")
    
    return {
        "message": f"JTI {jti} supprimé de la blacklist",
        "jti": jti,
        "admin_id": admin.id
    }


@router.get("/check/{jti}")
async def check_blacklist(
    jti: str,
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Vérifie si un JTI est dans la blacklist.
    Nécessite des droits administrateur.
    """
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JTI requis"
        )
    
    is_blacklisted = redis_client.is_blacklisted(jti)
    ttl = redis_client.get_blacklist_ttl(jti) if is_blacklisted else -1
    
    return {
        "jti": jti,
        "is_blacklisted": is_blacklisted,
        "ttl_remaining": ttl if ttl > 0 else None,
        "timestamp": datetime.utcnow().isoformat()
    }