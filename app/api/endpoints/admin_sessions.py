from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from ...models.session import SessionUtilisateur

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.session_service import SessionService
from ...schemas.session import (
    SessionSummaryResponse,
    SessionListResponse,
    SessionStatsResponse,
    SessionRevokeRequest,
    SessionWithUserResponse
)
from ...schemas.auth import UserAuthResponse
from ...models.role import Role
from ...schemas.session import SessionStatsResponse, SessionRevokeRequest
from ...services.cleanup_service import CleanupService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/sessions", tags=["Admin - Sessions"])

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

@router.get("/users/{user_id}", response_model=List[SessionSummaryResponse])
async def get_user_sessions(
    user_id: int,
    include_revoked: bool = Query(False, description="Inclure les sessions révoquées"),
    limit: int = Query(50, ge=1, le=100, description="Nombre maximum de sessions"),
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Récupère toutes les sessions d'un utilisateur spécifique.
    Nécessite des droits administrateur.
    """
    # Vérifier que l'utilisateur existe
    user = db.query(Utilisateur).filter(Utilisateur.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur introuvable"
        )
    
    if include_revoked:
        sessions = SessionService.get_user_all_sessions(db, user_id, limit=limit)
    else:
        sessions = SessionService.get_user_active_sessions(db, user_id, limit=limit)
    
    return [
        SessionSummaryResponse(
            session_uuid=str(s.session_uuid),
            date_connexion=s.date_connexion,
            date_derniere_activite=s.date_derniere_activite,
            date_fin=s.date_fin,
            est_revoquee=s.est_revoquee,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            device_info=s.session_data.get("device_info") if s.session_data else None
        )
        for s in sessions
    ]


@router.get("/user/{user_id}/active", response_model=List[SessionSummaryResponse])
async def get_user_active_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Récupère uniquement les sessions actives d'un utilisateur.
    Nécessite des droits administrateur.
    """
    user = db.query(Utilisateur).filter(Utilisateur.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur introuvable"
        )
    
    sessions = SessionService.get_user_active_sessions(db, user_id)
    
    return [
        SessionSummaryResponse(
            session_uuid=str(s.session_uuid),
            date_connexion=s.date_connexion,
            date_derniere_activite=s.date_derniere_activite,
            date_fin=s.date_fin,
            est_revoquee=s.est_revoquee,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            device_info=s.session_data.get("device_info") if s.session_data else None
        )
        for s in sessions
    ]


@router.get("/active", response_model=List[SessionWithUserResponse])
async def get_all_active_sessions(
    skip: int = Query(0, ge=0, description="Nombre d'éléments à sauter"),
    limit: int = Query(50, ge=1, le=100, description="Nombre maximum de sessions"),
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Récupère toutes les sessions actives du système.
    Nécessite des droits administrateur.
    """
    # Récupérer toutes les sessions actives avec pagination
    query = db.query(SessionUtilisateur).filter(
        SessionUtilisateur.est_revoquee == False
    ).order_by(SessionUtilisateur.date_connexion.desc())
    
    total = query.count()
    sessions = query.offset(skip).limit(limit).all()
    
    result = []
    for session in sessions:
        user = db.query(Utilisateur).filter(Utilisateur.id == session.user_id).first()
        user_response = None
        if user:
            user_response = UserAuthResponse(
                id=user.id,
                email=user.email,
                nom=user.nom,
                post_nom=user.post_nom,
                prenom=user.prenom,
                telephone=user.telephone,
                roles=[user.role.nom] if user.role else [],
                est_actif=user.est_actif,
                last_login=user.last_login
            )
        
        result.append(SessionWithUserResponse(
            session_uuid=str(session.session_uuid),
            date_connexion=session.date_connexion,
            date_derniere_activite=session.date_derniere_activite,
            date_fin=session.date_fin,
            est_revoquee=session.est_revoquee,
            ip_address=session.ip_address,
            user_agent=session.user_agent,
            device_info=session.session_data.get("device_info") if session.session_data else None,
            user=user_response
        ))
    
    return result


@router.post("/{session_uuid}/revoke")
async def revoke_session(
    session_uuid: str,
    request: SessionRevokeRequest,
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Révoque une session spécifique à distance.
    Nécessite des droits administrateur.
    """
    # Vérifier que la session existe
    session = SessionService.get_session_by_uuid(db, session_uuid)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session introuvable"
        )
    
    # Si revoke_all est true, révoquer toutes les sessions de l'utilisateur
    if request.revoke_all:
        user = db.query(Utilisateur).filter(Utilisateur.id == session.user_id).first()
        if user:
            revoked_count = user.revoke_all_sessions(db)
            logger.info(
                f"Admin {admin.id} a révoqué toutes les sessions de l'utilisateur {session.user_id} "
                f"({revoked_count} sessions)"
            )
            return {
                "message": f"Toutes les sessions de l'utilisateur {user.email} ont été révoquées",
                "revoked_count": revoked_count
            }
    
    # Révoquer la session spécifique
    success = SessionService.revoke_session(
        db, 
        session_uuid, 
        reason=request.reason or f"Révocation par admin {admin.id}"
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la révocation de la session"
        )
    
    logger.info(f"Admin {admin.id} a révoqué la session {session_uuid} (Raison: {request.reason})")
    
    return {
        "message": f"Session {session_uuid} révoquée avec succès",
        "session_uuid": session_uuid,
        "reason": request.reason
    }


@router.get("/stats", response_model=SessionStatsResponse)
async def get_session_stats(
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Récupère des statistiques sur les sessions.
    Nécessite des droits administrateur.
    """
    return SessionService.get_session_stats(db)


@router.delete("/cleanup")
async def cleanup_sessions(
    active_retention_days: int = Query(30, ge=1, description="Jours de rétention pour les sessions actives"),
    revoked_retention_days: int = Query(7, ge=1, description="Jours de rétention pour les sessions révoquées"),
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Nettoie les sessions anciennes.
    Nécessite des droits administrateur.
    """
    deleted_count = SessionService.cleanup_old_sessions(
        db, 
        active_retention_days=active_retention_days,
        revoked_retention_days=revoked_retention_days
    )
    
    return {
        "message": f"Nettoyage effectué avec succès",
        "deleted_sessions": deleted_count,
        "active_retention_days": active_retention_days,
        "revoked_retention_days": revoked_retention_days
    }

@router.get("/cleanup/status")
async def get_cleanup_status(
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Récupère le statut du service de nettoyage automatique.
    Nécessite des droits administrateur.
    """
    from app.main import cleanup_service
    
    if cleanup_service is None:
        return {
            "status": "not_initialized",
            "message": "Le service de nettoyage n'est pas initialisé"
        }
    
    return cleanup_service.get_status()


# Route pour déclencher manuellement le nettoyage
@router.post("/cleanup/run")
async def run_cleanup_manually(
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(require_admin)
):
    """
    Déclenche manuellement le nettoyage des sessions.
    Nécessite des droits administrateur.
    """
    from app.services.cleanup_service import CleanupService
    
    # Créer une instance temporaire pour exécuter le nettoyage
    service = CleanupService()
    
    try:
        service._cleanup_database()
        service._cleanup_redis()
        service._security_check()
        
        return {
            "message": "Nettoyage manuel exécuté avec succès",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage manuel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du nettoyage: {str(e)}"
        )