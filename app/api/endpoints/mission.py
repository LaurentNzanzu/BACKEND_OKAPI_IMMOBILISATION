from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.dependencies import get_current_organisation_id
from app.core.security import get_current_user
from app.core.dependencies_modules import require_module
from app.core.dependencies_permissions import require_permission, require_any_permission
from app.models.utilisateur import Utilisateur
from app.schemas.mission import (
    MissionCreate,
    MissionUpdate,
    MissionRead,
    MissionRejetPayload,
    MissionDemarrerPayload,
    MissionTerminerPayload,
    MissionAnnulerPayload,
)
from app.services import mission_service
from app.services.mission_service import (
    MissionWorkflowError,
    MissionPermissionError,
    MissionQuotaExceeded,
)
from app.services.affectation_service import AffectationConflict, create_affectation


router = APIRouter(
    prefix="/missions",
    tags=["Missions"],
    dependencies=[Depends(require_module("MISSION"))],
)


class MissionAffecterPayload(BaseModel):
    vehicule_id: int = Field(..., description="ID du véhicule patrimonial")
    chauffeur_id: int = Field(..., description="ID du chauffeur")
    date_debut: datetime = Field(..., description="Date et heure de début prévue")
    date_fin: datetime = Field(..., description="Date et heure de fin prévue")
    commentaire: str | None = None


@router.get("/", response_model=list[MissionRead], dependencies=[Depends(require_permission("MISSION_VOIR"))])
def list_missions(
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    skip: int = 0,
    limit: int = Query(100, le=500),
    statut: str | None = None,
    chauffeur_id: int | None = None,
    vehicule_id: int | None = None,
    projet_id: int | None = None,
    date_debut: datetime | None = None,
    date_fin: datetime | None = None,
    search: str | None = None,
):
    return mission_service.list_missions(
        db=db,
        organisation_id=organisation_id,
        skip=skip,
        limit=limit,
        statut=statut,
        chauffeur_id=chauffeur_id,
        vehicule_id=vehicule_id,
        projet_id=projet_id,
        date_debut=date_debut,
        date_fin=date_fin,
        search=search,
    )


@router.get("/{mission_id}", response_model=MissionRead, dependencies=[Depends(require_permission("MISSION_VOIR"))])
def get_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
):
    obj = mission_service.get_mission(db, mission_id, organisation_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    return obj


@router.post("/", response_model=MissionRead, status_code=201,
             dependencies=[Depends(require_permission("MISSION_CREATE"))])
def create_mission(
    payload: MissionCreate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        return mission_service.create_mission(db, payload, organisation_id, current_user.id)
    except MissionQuotaExceeded as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{mission_id}", response_model=MissionRead,
            dependencies=[Depends(require_permission("MISSION_MODIFIER"))])
def update_mission(
    mission_id: int,
    payload: MissionUpdate,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        obj = mission_service.update_mission(db, mission_id, payload, organisation_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not obj:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    return obj


@router.delete("/{mission_id}", status_code=204,
               dependencies=[Depends(require_permission("MISSION_SUPPRIMER"))])
def delete_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        ok = mission_service.delete_mission(db, mission_id, organisation_id, user_id=current_user.id)
        if not ok:
            raise HTTPException(status_code=404, detail="Mission introuvable")
    except MissionWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{mission_id}/soumettre", response_model=MissionRead)
def soumettre_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        return mission_service.soumettre_mission(db, mission_id, organisation_id, current_user)
    except MissionWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{mission_id}/valider", response_model=MissionRead)
def valider_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        return mission_service.valider_mission(db, mission_id, organisation_id, current_user)
    except MissionPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except MissionWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AffectationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{mission_id}/rejeter", response_model=MissionRead)
def rejeter_mission(
    mission_id: int,
    payload: MissionRejetPayload,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        return mission_service.rejeter_mission(db, mission_id, organisation_id, payload.motif, current_user)
    except MissionPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except MissionWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{mission_id}/affecter", dependencies=[Depends(require_permission("MISSION_AFFECTER"))])
def affecter_mission(
    mission_id: int,
    payload: MissionAffecterPayload,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        aff = create_affectation(
            db=db,
            data={
                "mission_id": mission_id,
                "vehicule_id": payload.vehicule_id,
                "chauffeur_id": payload.chauffeur_id,
                "date_debut": payload.date_debut,
                "date_fin": payload.date_fin,
                "commentaire": payload.commentaire,
            },
            organisation_id=organisation_id,
            user_id=current_user.id,
        )
        return {"message": "Affectation réussie", "affectation_id": aff.id}
    except AffectationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{mission_id}/demarrer", response_model=MissionRead,
             dependencies=[Depends(require_any_permission("MISSION_AFFECTER", "MISSION_CREATE", "MISSION_MODIFIER"))])
def demarrer_mission(
    mission_id: int,
    payload: MissionDemarrerPayload,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        return mission_service.demarrer_mission(
            db=db,
            mission_id=mission_id,
            km_depart=payload.km_depart,
            heure_depart=payload.heure_depart or datetime.utcnow(),
            organisation_id=organisation_id,
            user_id=current_user.id,
            photo_depart_url=payload.photo_depart_url,
        )
    except MissionWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{mission_id}/terminer", response_model=MissionRead,
             dependencies=[Depends(require_any_permission("MISSION_CLOSE", "MISSION_MODIFIER"))])
def terminer_mission(
    mission_id: int,
    payload: MissionTerminerPayload,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        return mission_service.terminer_mission(
            db=db,
            mission_id=mission_id,
            km_arrivee=payload.km_arrivee,
            heure_retour=payload.heure_retour or datetime.utcnow(),
            organisation_id=organisation_id,
            user_id=current_user.id,
            observation=payload.observation,
        )
    except MissionWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{mission_id}/annuler", response_model=MissionRead,
             dependencies=[Depends(require_any_permission("MISSION_MODIFIER", "MISSION_CREATE"))])
def annuler_mission(
    mission_id: int,
    payload: MissionAnnulerPayload,
    db: Session = Depends(get_db),
    organisation_id: int = Depends(get_current_organisation_id),
    current_user: Utilisateur = Depends(get_current_user),
):
    try:
        return mission_service.annuler_mission(
            db=db,
            mission_id=mission_id,
            motif=payload.motif,
            organisation_id=organisation_id,
            user_id=current_user.id,
        )
    except MissionWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))