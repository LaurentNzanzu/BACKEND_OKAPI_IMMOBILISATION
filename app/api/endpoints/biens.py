# backend/app/api/endpoints/biens.py
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import io
from typing import List, Optional
import logging

from ...core.database import get_db
from ...core.bien_permissions import (
    can_view_biens,
    can_view_financial_data,
    can_create_bien,
    can_delete_bien,
    can_update_bien,
    can_view_bien_detail,
    get_user_role,
    filter_bien_update,
    sanitize_bien_dict,
    log_access_denied,
    log_access_granted,
)
from ...schemas.bien import BienCreate, BienUpdate, BienResponse, BienListResponse
from ...schemas.fournisseur import FournisseurResponse
from ...services.bien_service import BienService
from ...services.fournisseur_service import FournisseurService
from ...services.comptabilite_service import ComptabiliteService
from ...services.qr_code_service import QRCodeService
from ...services.audit_service import AuditService
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...models.bien import EtatBien

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/biens", tags=["Biens"])


def _to_bien_response(bien, user: Utilisateur) -> BienResponse:
    data = BienResponse.model_validate(bien).model_dump()
    data = sanitize_bien_dict(data, user)
    return BienResponse.model_validate(data)


def _deny(user: Utilisateur, action: str, detail: str, request: Request = None, resource_id: int = None):
    log_access_denied(user, action, detail=detail, request=request, resource_id=resource_id)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@router.post("/", response_model=BienResponse, status_code=status.HTTP_201_CREATED)
async def create_bien(
    bien_data: BienCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    audit_service = AuditService(db)

    if not can_create_bien(current_user):
        _deny(current_user, "create_bien", "Permissions insuffisantes pour créer un bien", request)

    # Vérification du fournisseur si mode paiement = credit
    if bien_data.mode_paiement == "credit" and bien_data.fournisseur_id:
        fournisseur = FournisseurService(db).get_by_id(bien_data.fournisseur_id)
        if not fournisseur:
            raise HTTPException(status_code=404, detail="Fournisseur non trouvé")

    service = BienService(db)
    
    try:
        bien = service.create_bien(bien_data)
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création bien: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    # Audit
    audit_service.log_create(
        user_id=current_user.id,
        table_name="biens",
        record_id=bien.id_bien,
        new_values={
            "type_bien": bien.type_bien,
            "marque": getattr(bien, "marque", getattr(bien, "fabricant", None)),
            "modele": getattr(bien, "modele", None),
            "prix_acquisition": float(bien.prix_acquisition) if bien.prix_acquisition else None,
            "mode_paiement": bien.mode_paiement,
            "qr_code": bien.qr_code,
        },
        request=request,
    )

    return _to_bien_response(bien, current_user)


@router.get("", response_model=BienListResponse)
@router.get("/", response_model=BienListResponse, include_in_schema=False)
async def get_biens(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    type_bien: Optional[str] = None,
    etat: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not can_view_biens(current_user):
        _deny(current_user, "list_biens", "Permissions insuffisantes pour voir les biens", request)

    service = BienService(db)
    etat_enum = None
    if etat:
        try:
            etat_enum = EtatBien(etat.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"État invalide. Valeurs possibles: {[e.value for e in EtatBien]}",
            )

    if get_user_role(current_user) == "TECHNICIEN":
        biens = service.get_biens_for_technicien(
            current_user.id,
            skip=skip,
            limit=limit,
            type_bien=type_bien,
            etat=etat_enum,
        )
    else:
        biens = service.get_all_biens(skip=skip, limit=limit, type_bien=type_bien, etat=etat_enum)

    return BienListResponse(
        total=len(biens),
        page=(skip // limit) + 1,
        page_size=limit,
        biens=[_to_bien_response(b, current_user) for b in biens],
    )


@router.get("/{bien_id}", response_model=BienResponse)
async def get_bien(
    bien_id: int,
    panne_id: Optional[int] = Query(None, description="Contexte panne pour accès technicien"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    if not can_view_biens(current_user):
        _deny(current_user, "view_bien", "Permissions insuffisantes pour voir ce bien", request, bien_id)

    service = BienService(db)
    bien = service.get_bien_by_id(bien_id)
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    if not can_view_bien_detail(current_user, bien, db, panne_id):
        _deny(
            current_user,
            "view_bien_detail",
            "Accès refusé : ce bien n'est pas dans votre périmètre technicien",
            request,
            bien_id,
        )

    log_access_granted(
        current_user,
        "view_bien_detail",
        resource_id=bien_id,
        detail=f"panne_id={panne_id}" if panne_id else None,
        request=request,
    )

    return _to_bien_response(bien, current_user)


@router.put("/{bien_id}", response_model=BienResponse)
async def update_bien(
    bien_id: int,
    bien_data: BienUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    audit_service = AuditService(db)

    if not can_update_bien(current_user):
        _deny(
            current_user,
            "update_bien",
            "Permissions insuffisantes pour modifier un bien",
            request,
            bien_id,
        )

    service = BienService(db)
    old_bien = service.get_bien_by_id(bien_id)
    if not old_bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    filtered_data = filter_bien_update(current_user, bien_data)
    if not filtered_data.model_dump(exclude_unset=True):
        _deny(
            current_user,
            "update_bien_empty",
            "Aucun champ modifiable autorisé pour votre rôle",
            request,
            bien_id,
        )

    bien = service.update_bien(bien_id, filtered_data)
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    old_values = {
        "etat": old_bien.etat.value if old_bien.etat else None,
        "localisation": old_bien.localisation,
        "description": old_bien.description,
    }
    new_values = {
        "etat": bien.etat.value if bien.etat else None,
        "localisation": bien.localisation,
        "description": bien.description,
    }
    if can_view_financial_data(current_user):
        old_values["prix_acquisition"] = float(old_bien.prix_acquisition) if old_bien.prix_acquisition else None
        new_values["prix_acquisition"] = float(bien.prix_acquisition) if bien.prix_acquisition else None

    audit_service.log_update(
        user_id=current_user.id,
        table_name="biens",
        record_id=bien_id,
        old_values=old_values,
        new_values=new_values,
        request=request,
    )

    return _to_bien_response(bien, current_user)


@router.delete("/{bien_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bien(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    audit_service = AuditService(db)

    if not can_delete_bien(current_user):
        _deny(
            current_user,
            "delete_bien",
            "Permissions insuffisantes pour supprimer un bien",
            request,
            bien_id,
        )

    service = BienService(db)
    bien = service.get_bien_by_id(bien_id)
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    audit_service.log_delete(
        user_id=current_user.id,
        table_name="biens",
        record_id=bien_id,
        old_values={
            "type_bien": bien.type_bien,
            "marque": getattr(bien, "marque", getattr(bien, "fabricant", None)),
            "modele": getattr(bien, "modele", None),
            "qr_code": bien.qr_code,
        },
        request=request,
    )

    if not service.delete_bien(bien_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")


@router.get("/{bien_id}/qr-code")
async def get_bien_qr_code(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not can_view_biens(current_user):
        _deny(current_user, "view_qr", "Permissions insuffisantes", resource_id=bien_id)

    service = BienService(db)
    bien = service.get_bien_by_id(bien_id)
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    qr_service = QRCodeService()
    qr_code_image = qr_service.generate_qr_code(bien.qr_code, bien_id)

    return StreamingResponse(
        io.BytesIO(qr_code_image),
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=qr_code_{bien_id}.png"},
    )


@router.get("/{bien_id}/age")
async def get_bien_age(
    bien_id: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not can_view_biens(current_user):
        _deny(current_user, "view_bien_age", "Permissions insuffisantes", resource_id=bien_id)

    service = BienService(db)
    age = service.calculer_age_bien(bien_id)
    if age is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    return {"bien_id": bien_id, "age_years": age}


@router.patch("/{bien_id}/etat")
async def change_bien_etat(
    bien_id: int,
    nouvel_etat: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None,
):
    audit_service = AuditService(db)

    if not can_update_bien(current_user):
        _deny(
            current_user,
            "change_etat",
            "Permissions insuffisantes pour modifier l'état d'un bien",
            request,
            bien_id,
        )

    service = BienService(db)
    old_bien = service.get_bien_by_id(bien_id)
    if not old_bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    try:
        etat = EtatBien(nouvel_etat)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"État invalide. Valeurs possibles: {[e.value for e in EtatBien]}",
        )

    bien = service.changer_etat_bien(bien_id, etat)
    if not bien:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bien {bien_id} non trouvé")

    audit_service.log_update(
        user_id=current_user.id,
        table_name="biens",
        record_id=bien_id,
        old_values={"etat": old_bien.etat.value if old_bien.etat else None},
        new_values={"etat": nouvel_etat},
        request=request,
    )

    return _to_bien_response(bien, current_user)


@router.get("/statistics/summary")
async def get_biens_statistics(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    if not can_view_biens(current_user):
        _deny(current_user, "biens_statistics", "Permissions insuffisantes")

    service = BienService(db)
    stats = service.get_statistics()

    if not can_view_financial_data(current_user):
        stats.pop("valeur_totale", None)

    return stats