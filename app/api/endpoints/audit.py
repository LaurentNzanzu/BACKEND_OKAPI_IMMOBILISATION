from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...services.audit_service import AuditService
from ...models.audit_log import AuditLog
from ...schemas.audit import AuditLogResponse, AuditLogListResponse

router = APIRouter(prefix="/audit", tags=["Audit"])

def check_audit_permission(user: Utilisateur):
    if not user or not user.role:
        return False
    role = user.role.nom.upper()
    return role in ["ADMIN", "DG"]

@router.get("/", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    utilisateur_id: Optional[int] = None,
    table: Optional[str] = None,
    action: Optional[str] = None,
    date_debut: Optional[datetime] = None,
    date_fin: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_audit_permission(current_user):
        raise HTTPException(status_code=403, detail="Accès réservé à l'administration")

    service = AuditService(db)
    items, total = service.get_logs(
        utilisateur_id=utilisateur_id,
        table=table,
        action=action,
        date_debut=date_debut,
        date_fin=date_fin,
        page=page,
        page_size=page_size
    )

    return AuditLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            AuditLogResponse(
                id_log=log.id_log,
                table_concernee=log.table_concernee,
                id_enregistrement=log.id_enregistrement,
                action=log.action,
                anciennes_valeurs=log.anciennes_valeurs,
                nouvelles_valeurs=log.nouvelles_valeurs,
                adresse_ip=log.adresse_ip,
                user_agent=log.user_agent,
                date_action=log.date_action,
                id_utilisateur=log.id_utilisateur,
                utilisateur_nom=log.utilisateur.nom if log.utilisateur else None,
                utilisateur_email=log.utilisateur.email if log.utilisateur else None
            )
            for log in items
        ]
    )

@router.get("/user/{user_id}")
async def get_user_audit_history(
    user_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_audit_permission(current_user):
        raise HTTPException(status_code=403, detail="Accès réservé à l'administration")

    service = AuditService(db)
    logs = service.get_user_history(user_id, limit)
    return [
        {
            "id_log": log.id_log,
            "action": log.action,
            "table_concernee": log.table_concernee,
            "id_enregistrement": log.id_enregistrement,
            "date_action": log.date_action,
            "anciennes_valeurs": log.anciennes_valeurs,
            "nouvelles_valeurs": log.nouvelles_valeurs
        }
        for log in logs
    ]

@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log_by_id(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupérer un log d'audit spécifique par son ID"""
    if not check_audit_permission(current_user):
        raise HTTPException(status_code=403, detail="Accès réservé à l'administration")
    
    log = db.query(AuditLog).filter(AuditLog.id_log == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log d'audit non trouvé")
    
    return AuditLogResponse(
        id_log=log.id_log,
        table_concernee=log.table_concernee,
        id_enregistrement=log.id_enregistrement,
        action=log.action,
        anciennes_valeurs=log.anciennes_valeurs,
        nouvelles_valeurs=log.nouvelles_valeurs,
        adresse_ip=log.adresse_ip,
        user_agent=log.user_agent,
        date_action=log.date_action,
        id_utilisateur=log.id_utilisateur,
        utilisateur_nom=log.utilisateur.nom if log.utilisateur else None,
        utilisateur_email=log.utilisateur.email if log.utilisateur else None
    )

@router.get("/table/{table_name}/{record_id}")
async def get_record_audit_history(
    table_name: str,
    record_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    if not check_audit_permission(current_user):
        raise HTTPException(status_code=403, detail="Accès réservé à l'administration")

    service = AuditService(db)
    logs = service.get_record_history(table_name, record_id, limit)
    return [
        {
            "id_log": log.id_log,
            "action": log.action,
            "date_action": log.date_action,
            "utilisateur": log.utilisateur.nom if log.utilisateur else "Système",
            "anciennes_valeurs": log.anciennes_valeurs,
            "nouvelles_valeurs": log.nouvelles_valeurs
        }
        for log in logs
    ]