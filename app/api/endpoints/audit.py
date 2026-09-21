# backend/app/api/endpoints/audit.py
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


# ═══ AJOUT 5.19 — Helpers d'isolation multi-tenant ═══
def _is_platform_admin(user: Utilisateur) -> bool:
    return bool(getattr(user, "is_platform_admin", False))


def _get_organisation_cible(current_user: Utilisateur) -> Optional[int]:
    """
    Retourne l'organisation_id à utiliser pour filtrer les logs :
    - ADMIN plateforme → None (accès total)
    - Sinon → current_user.organisation_id (obligatoire)
    """
    if _is_platform_admin(current_user):
        return None
    return current_user.organisation_id


def _check_acces_log(db: Session, current_user: Utilisateur, log: AuditLog) -> None:
    """
    Vérifie l'accès à un log d'audit.
    - ADMIN plateforme → passe
    - Log système (id_utilisateur NULL) → réservé à l'ADMIN plateforme
    - Sinon : le log doit avoir été généré par un utilisateur de la même ONG
    """
    if _is_platform_admin(current_user):
        return

    if log.id_utilisateur is None:
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : ce log système est réservé à l'administrateur plateforme.",
        )

    # Vérifier l'organisation de l'auteur du log
    auteur = db.query(Utilisateur).filter(Utilisateur.id == log.id_utilisateur).first()
    auteur_org = getattr(auteur, "organisation_id", None) if auteur else None

    if auteur_org is None:
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : auteur du log sans organisation.",
        )

    if auteur_org != current_user.organisation_id:
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : ce log appartient à une autre organisation.",
        )
# ═══ FIN AJOUT 5.19 ═══


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

    # ═══ MODIF 5.19 — Filtrage multi-tenant ═══
    organisation_id = _get_organisation_cible(current_user)
    # ═══ FIN MODIF 5.19 ═══

    service = AuditService(db)
    items, total = service.get_logs(
        utilisateur_id=utilisateur_id,
        table=table,
        action=action,
        date_debut=date_debut,
        date_fin=date_fin,
        page=page,
        page_size=page_size,
        organisation_id=organisation_id,  # ═══ AJOUT 5.19 ═══
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

    # ═══ MODIF 5.19 — Vérification d'accès sur l'utilisateur ciblé ═══
    if not _is_platform_admin(current_user):
        cible = db.query(Utilisateur).filter(Utilisateur.id == user_id).first()
        if not cible:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        if getattr(cible, "organisation_id", None) != current_user.organisation_id:
            raise HTTPException(
                status_code=403,
                detail="Accès refusé : cet utilisateur appartient à une autre organisation.",
            )
    # ═══ FIN MODIF 5.19 ═══

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

    # ═══ MODIF 5.19 — Vérification d'accès ═══
    _check_acces_log(db, current_user, log)
    # ═══ FIN MODIF 5.19 ═══

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

    # ═══ MODIF 5.19 — Filtrage multi-tenant ═══
    organisation_id = _get_organisation_cible(current_user)
    # ═══ FIN MODIF 5.19 ═══

    service = AuditService(db)
    logs = service.get_record_history(
        table_name, record_id, limit,
        organisation_id=organisation_id,  # ═══ AJOUT 5.19 ═══
    )
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