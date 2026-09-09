# backend/app/api/endpoints/types_biens.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from ...core.database import get_db
from ...core.security import get_current_user
from ...core.bien_permissions import can_view_biens, can_create_bien, can_update_bien, can_delete_bien, log_access_denied
from ...models.utilisateur import Utilisateur
from ...models.type_bien import TypeBien
from ...schemas.type_bien import (
    TypeBienCreate, TypeBienUpdate, TypeBienResponse, TypeBienListResponse
)
from ...services.type_bien_service import TypeBienService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/types-biens", tags=["Types de Biens"])


def _deny(user: Utilisateur, action: str, detail: str, request: Request = None, resource_id: int = None):
    log_access_denied(user, action, detail=detail, request=request, resource_id=resource_id)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def check_type_bien_permission(user: Utilisateur, action: str = "view") -> bool:
    """Vérifie les permissions sur les types de biens."""
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN","COMPTABLE"] and action in ["view", "create", "update", "delete"]:
        return True
    if role in ["DG", "COMPTABLE"] and action in ["view"]:
        return True
    return False


# ============================================================
# ENDPOINTS CRUD
# ============================================================

@router.get("", response_model=TypeBienListResponse)
@router.get("/", response_model=TypeBienListResponse, include_in_schema=False)
async def get_types_biens(
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=500),
    est_actif: Optional[bool] = Query(None, description="Filtrer par statut actif/inactif"),
    search: Optional[str] = Query(None, description="Recherche par libellé ou code"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Récupère la liste des types de biens avec pagination et filtres.
    """
    if not check_type_bien_permission(current_user, "view"):
        _deny(current_user, "list_types_biens", "Permissions insuffisantes pour voir les types de biens", request)

    service = TypeBienService(db)
    
    try:
        types = service.get_all(
            skip=skip,
            limit=limit,
            est_actif=est_actif,
            search=search
        )
        
        total_count = service.get_count(
            est_actif=est_actif,
            search=search
        )
        
        return TypeBienListResponse(
            total=total_count,
            page=(skip // limit) + 1,
            page_size=limit,
            types=types
        )
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des types de biens: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@router.get("/all", response_model=List[TypeBienResponse])
async def get_all_types_biens(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Récupère tous les types de biens actifs (sans pagination).
    Utilisé pour les listes déroulantes du frontend.
    """
    if not check_type_bien_permission(current_user, "view"):
        _deny(current_user, "list_all_types_biens", "Permissions insuffisantes", request)

    service = TypeBienService(db)
    types = service.get_all(est_actif=True, limit=1000)
    return types


@router.get("/{type_id}", response_model=TypeBienResponse)
async def get_type_bien(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Récupère un type de bien par son ID.
    """
    if not check_type_bien_permission(current_user, "view"):
        _deny(current_user, "get_type_bien", "Permissions insuffisantes", request, type_id)

    service = TypeBienService(db)
    type_bien = service.get_by_id(type_id)
    
    if not type_bien:
        raise HTTPException(status_code=404, detail="Type de bien non trouvé")
    
    return type_bien


@router.post("/", response_model=TypeBienResponse, status_code=status.HTTP_201_CREATED)
async def create_type_bien(
    data: TypeBienCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Crée un nouveau type de bien.
    Seul un administrateur peut créer des types de biens.
    """
    if not check_type_bien_permission(current_user, "create"):
        _deny(current_user, "create_type_bien", "Permissions insuffisantes pour créer un type de bien", request)

    service = TypeBienService(db)
    audit_service = AuditService(db)
    
    try:
        type_bien = service.create(data)
        
        audit_service.log_create(
            user_id=current_user.id,
            table_name="types_biens",
            record_id=type_bien.id,
            new_values={
                "libelle": type_bien.libelle,
                "code": type_bien.code,
                "compte_comptable": type_bien.compte_comptable,
                "champs_specifiques": type_bien.champs_specifiques
            },
            request=request
        )
        
        return type_bien
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur lors de la création du type de bien: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@router.put("/{type_id}", response_model=TypeBienResponse)
async def update_type_bien(
    type_id: int,
    data: TypeBienUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Met à jour un type de bien.
    Seul un administrateur peut modifier les types de biens.
    """
    if not check_type_bien_permission(current_user, "update"):
        _deny(current_user, "update_type_bien", "Permissions insuffisantes pour modifier un type de bien", request, type_id)

    service = TypeBienService(db)
    audit_service = AuditService(db)
    
    old_type = service.get_by_id(type_id)
    if not old_type:
        raise HTTPException(status_code=404, detail="Type de bien non trouvé")
    
    try:
        type_bien = service.update(type_id, data)
        
        audit_service.log_update(
            user_id=current_user.id,
            table_name="types_biens",
            record_id=type_id,
            old_values={
                "libelle": old_type.libelle,
                "code": old_type.code,
                "est_actif": old_type.est_actif
            },
            new_values={
                "libelle": type_bien.libelle,
                "code": type_bien.code,
                "est_actif": type_bien.est_actif
            },
            request=request
        )
        
        return type_bien
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour du type de bien: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_type_bien(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Supprime un type de bien (suppression logique - désactivation).
    Seul un administrateur peut supprimer les types de biens.
    """
    if not check_type_bien_permission(current_user, "delete"):
        _deny(current_user, "delete_type_bien", "Permissions insuffisantes pour supprimer un type de bien", request, type_id)

    service = TypeBienService(db)
    audit_service = AuditService(db)
    
    type_bien = service.get_by_id(type_id)
    if not type_bien:
        raise HTTPException(status_code=404, detail="Type de bien non trouvé")
    
    # Vérifier si le type est utilisé par des biens
    if service.is_used_by_biens(type_id):
        raise HTTPException(
            status_code=400,
            detail="Ce type de bien est utilisé par des biens existants. Vous ne pouvez pas le supprimer."
        )
    
    try:
        service.delete(type_id)
        
        audit_service.log_delete(
            user_id=current_user.id,
            table_name="types_biens",
            record_id=type_id,
            old_values={
                "libelle": type_bien.libelle,
                "code": type_bien.code
            },
            request=request
        )
        
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du type de bien: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@router.get("/{type_id}/champs", response_model=List[dict])
async def get_champs_specifiques(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Récupère les champs spécifiques d'un type de bien.
    Utilisé par le frontend pour générer le formulaire dynamique.
    """
    if not check_type_bien_permission(current_user, "view"):
        _deny(current_user, "get_champs_specifiques", "Permissions insuffisantes", request, type_id)

    service = TypeBienService(db)
    type_bien = service.get_by_id(type_id)
    
    if not type_bien:
        raise HTTPException(status_code=404, detail="Type de bien non trouvé")
    
    return type_bien.champs_specifiques or []


@router.post("/{type_id}/champs", response_model=TypeBienResponse)
async def ajouter_champ_specifique(
    type_id: int,
    champ: dict,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Ajoute un champ spécifique à un type de bien.
    """
    if not check_type_bien_permission(current_user, "update"):
        _deny(current_user, "ajouter_champ_specifique", "Permissions insuffisantes", request, type_id)

    service = TypeBienService(db)
    
    # Valider le champ
    required_keys = ["nom", "type"]
    for key in required_keys:
        if key not in champ:
            raise HTTPException(status_code=400, detail=f"Le champ '{key}' est obligatoire")
    
    try:
        type_bien = service.ajouter_champ(type_id, champ)
        return type_bien
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur lors de l'ajout du champ spécifique: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")


@router.delete("/{type_id}/champs/{champ_nom}", response_model=TypeBienResponse)
async def supprimer_champ_specifique(
    type_id: int,
    champ_nom: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """
    Supprime un champ spécifique d'un type de bien.
    """
    if not check_type_bien_permission(current_user, "update"):
        _deny(current_user, "supprimer_champ_specifique", "Permissions insuffisantes", request, type_id)

    service = TypeBienService(db)
    
    try:
        type_bien = service.supprimer_champ(type_id, champ_nom)
        return type_bien
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur lors de la suppression du champ spécifique: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")