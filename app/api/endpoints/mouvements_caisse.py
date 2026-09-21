# backend/app/api/endpoints/mouvements_caisse.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date  # ═══ AJOUT 5.9 — date ═══
import os

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.mouvement_caisse import (
    MouvementCaisseCreate, MouvementCaisseResponse, MouvementCaisseListResponse,
    ApprovisionnementCaisseRequest, ValidationMouvementRequest, SignatureDGRequest
)
from ...services.mouvement_caisse_service import MouvementCaisseService

# ═══════════════ AJOUT 5.9 — IMPORTS TAUX CHANGE (DÉBUT) ═══════════════
from ...services.taux_change_service import TauxChangeService
from ...schemas.taux_change import ConversionResponse
# ═══════════════ AJOUT 5.9 — IMPORTS TAUX CHANGE (FIN) ═══════════════

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


# ═══════════════════════════════════════════════════════════════════════════
# ═══ AJOUT 5.9 — ENDPOINT MOUVEMENT MULTI-DEVISE (DÉBUT)                 ═══
# ═══════════════════════════════════════════════════════════════════════════
# Isolation multi-tenant stricte :
#   - Non-plateforme : organisation_id = current_user.organisation_id (forcé)
#   - Plateforme     : organisation_id obligatoire en query
#   - Vérification que la caisse ciblée appartient bien à cette organisation
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/mouvements/multi-devise")
def creer_mouvement_multi_devise(
    data: MouvementCaisseCreate,
    devise_source: str = Query(
        ..., min_length=3, max_length=3,
        description="Devise dans laquelle le montant est exprimé (ex: USD)",
    ),
    devise_cible: str = Query(
        ..., min_length=3, max_length=3,
        description="Devise cible (doit correspondre à la devise de la caisse)",
    ),
    date_reference: Optional[date] = Query(
        None, description="Date de référence pour le taux (défaut : aujourd'hui)",
    ),
    organisation_id: Optional[int] = Query(
        None,
        description="Requis uniquement pour un ADMIN plateforme. Sinon, ignoré.",
    ),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Crée un mouvement de caisse avec **conversion devise automatique**.

    Logique :
      1. Si `devise_source == devise_cible` → identité, pas de conversion.
      2. Sinon → récupère le taux applicable pour l'organisation et la date,
         convertit le montant, puis crée le mouvement dans la devise cible.
      3. Retourne le mouvement créé + les informations de conversion.

    Rôles autorisés : ADMIN, DG, CAISSE, COMPTABLE.
    """
    # --- 1. Contrôle de rôle ---
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG", "CAISSE", "COMPTABLE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    # --- 2. Isolation multi-tenant : détermination de l'organisation cible ---
    is_platform = getattr(current_user, "is_platform_admin", False)

    if is_platform:
        if not organisation_id:
            raise HTTPException(
                status_code=400,
                detail="organisation_id est requis pour un ADMIN plateforme.",
            )
        target_org = organisation_id
    else:
        target_org = current_user.organisation_id
        if not target_org:
            # Cas anormal : utilisateur non plateforme sans organisation
            raise HTTPException(
                status_code=403,
                detail="Utilisateur sans organisation — action interdite.",
            )

    # --- 3. Récupérer la caisse + vérifier son appartenance à l'organisation ---
    from ...models.caisse import Caisse
    caisse = db.query(Caisse).filter(Caisse.id_caisse == data.id_caisse).first()
    if not caisse:
        raise HTTPException(
            status_code=404,
            detail=f"Caisse #{data.id_caisse} introuvable",
        )

    caisse_org = getattr(caisse, "organisation_id", None)

    # Si la caisse a un organisation_id défini, il doit correspondre à target_org
    if caisse_org is not None and caisse_org != target_org:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cette caisse appartient à une autre organisation "
                f"(#{caisse_org}). Accès refusé."
            ),
        )

    # --- 4. Vérifier la cohérence des devises ---
    devise_caisse = (getattr(caisse, "devise", None) or "USD").upper()
    dev_s = devise_source.strip().upper()
    dev_c = devise_cible.strip().upper()

    if dev_c != devise_caisse:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La devise cible ({dev_c}) doit correspondre à la devise "
                f"de la caisse #{caisse.id_caisse} ({devise_caisse})."
            ),
        )

    # --- 5. Conversion si nécessaire ---
    taux_service = TauxChangeService(db)
    montant_origine = float(data.montant)

    try:
        conversion = taux_service.convertir(
            organisation_id=target_org,
            montant=montant_origine,
            devise_source=dev_s,
            devise_cible=dev_c,
            date_reference=date_reference,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    montant_converti = float(conversion["montant_converti"])

    # --- 6. Créer le mouvement dans la devise de la caisse (montant converti) ---
    data_convertie = data.model_copy(update={"montant": montant_converti})

    service = MouvementCaisseService(db)
    try:
        mvt = service.creer_mouvement(data_convertie)
        db.commit()
        db.refresh(mvt)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur interne : {e}")

    # --- 7. Retour : mouvement + info conversion ---
    return {
        "mouvement": MouvementCaisseResponse.model_validate(mvt).model_dump(),
        "conversion": ConversionResponse(
            montant_origine=conversion["montant_origine"],
            montant_converti=conversion["montant_converti"],
            taux=conversion["taux"],
            devise_source=conversion["devise_source"],
            devise_cible=conversion["devise_cible"],
            date_taux=conversion.get("date_taux"),
            source=conversion.get("source"),
        ).model_dump(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# ═══ AJOUT 5.9 — ENDPOINT MOUVEMENT MULTI-DEVISE (FIN)                   ═══
# ═══════════════════════════════════════════════════════════════════════════


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