# backend/app/api/endpoints/mouvements_caisse.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.mouvement_caisse import (
    MouvementCaisseCreate, MouvementCaisseResponse, MouvementCaisseListResponse,
    ApprovisionnementCaisseRequest, ValidationMouvementRequest, SignatureDGRequest
)
from ...services.mouvement_caisse_service import MouvementCaisseService

router = APIRouter(prefix="/caisse", tags=["Mouvements Caisse"])


@router.post("/mouvements", response_model=MouvementCaisseResponse)
def creer_mouvement(
    data: MouvementCaisseCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG", "CAISSE", "COMPTABLE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = MouvementCaisseService(db)
    try:
        mvt = service.creer_mouvement(data)
        db.commit()
        db.refresh(mvt)
        return mvt
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/mouvements", response_model=MouvementCaisseListResponse)
def lister_mouvements(
    type_mouvement: Optional[str] = Query(None, description="Filtre par type (ENTREE/SORTIE)"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = MouvementCaisseService(db)
    res = service.lister_mouvements(type_mouvement, page, limit)
    return res


@router.get("/mouvements/{id_mouvement}", response_model=MouvementCaisseResponse)
def obtenir_mouvement(
    id_mouvement: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = MouvementCaisseService(db)
    mouvement = service.obtenir_mouvement(id_mouvement)
    if not mouvement:
        raise HTTPException(status_code=404, detail="Mouvement non trouvé")
    return mouvement


@router.get("/mouvements/{id_mouvement}/pdf")
def telecharger_pdf_mouvement(
    id_mouvement: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = MouvementCaisseService(db)
    mouvement = service.obtenir_mouvement(id_mouvement)
    if not mouvement or not mouvement.piece_jointe_url:
        raise HTTPException(status_code=404, detail="PDF non trouvé pour ce mouvement")
    
    filepath = os.path.join(os.getcwd(), mouvement.piece_jointe_url.lstrip("/"))
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Fichier PDF inexistant sur le disque")
    
    return FileResponse(filepath, media_type="application/pdf", filename=os.path.basename(filepath))


@router.post("/mouvements/{id_mouvement}/valider", response_model=MouvementCaisseResponse)
def valider_mouvement(
    id_mouvement: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "CAISSE"]:
        raise HTTPException(status_code=403, detail="Seul le caissier ou l'administrateur peut valider le mouvement de caisse")
    service = MouvementCaisseService(db)
    try:
        mvt = service.valider_mouvement(id_mouvement, current_user.id)
        db.commit()
        db.refresh(mvt)
        return mvt
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/mouvements/{id_mouvement}/dg-sign", response_model=MouvementCaisseResponse)
def signature_dg(
    id_mouvement: int,
    data: SignatureDGRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG"]:
        raise HTTPException(status_code=403, detail="Seul le DG ou l'administrateur peut signer l'approbation de décaissement")
    service = MouvementCaisseService(db)
    try:
        mvt = service.signer_dg(id_mouvement, data.approuve, data.motif)
        db.commit()
        db.refresh(mvt)
        return mvt
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/solde")
def obtenir_solde(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    service = MouvementCaisseService(db)
    return service.get_solde_caisse()


@router.post("/approvisionner", response_model=MouvementCaisseResponse)
def approvisionner_caisse(
    data: ApprovisionnementCaisseRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG", "CAISSE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    # Récupérer la caisse principale active
    from ...models.caisse import Caisse
    caisse = db.query(Caisse).filter(Caisse.statut == "ACTIF").first()
    if not caisse:
        caisse = Caisse(solde_physique=0.0, solde_theorique=0.0, devise="USD", statut="ACTIF")
        db.add(caisse)
        db.commit()
        db.refresh(caisse)

    service = MouvementCaisseService(db)
    mvt_create = MouvementCaisseCreate(
        id_caisse=caisse.id_caisse,
        type_mouvement="ENTREE",
        montant=data.montant,
        motif=data.motif,
        origine_type="CAISSE",
        origine_id=caisse.id_caisse,
        mode_reglement=data.mode_reglement or "ESPECES",
        beneficiaire="Caisse Principale"
    )
    try:
        mvt = service.creer_mouvement(mvt_create)
        mvt_valide = service.valider_mouvement(mvt.id_mouvement, current_user.id)
        db.commit()
        db.refresh(mvt_valide)
        return mvt_valide
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
