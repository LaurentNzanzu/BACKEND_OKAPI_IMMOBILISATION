# backend/app/api/endpoints/caisse.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional  # ═══ AJOUT 5.8 — Optional ═══
from datetime import date         # ═══ AJOUT 5.8 — date ═══

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.caisse import CaisseCreate, CaisseUpdate, CaisseResponse, TresorerieVerificationResponse
from ...services.caisse_service import CaisseService

# ═══════════════ AJOUT 5.8 — IMPORTS TAUX CHANGE (DÉBUT) ═══════════════
from ...services.taux_change_service import TauxChangeService
from ...schemas.taux_change import (
    TauxChangeCreate,
    TauxChangeResponse,
    ConversionRequest,
    ConversionResponse,
)
# ═══════════════ AJOUT 5.8 — IMPORTS TAUX CHANGE (FIN) ═══════════════

router = APIRouter(prefix="/caisses", tags=["Caisses"])


@router.get("/verifier-tresorerie", response_model=TresorerieVerificationResponse)
def verifier_tresorerie(
    montant: float = Query(..., gt=0, description="Montant à vérifier en caisse"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Vérifie si le solde physique disponible en caisse est suffisant."""
    service = CaisseService(db)
    return service.verifier_tresorerie(montant)


@router.get("/", response_model=List[CaisseResponse])
def lister_caisses(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Liste toutes les caisses enregistrées."""
    service = CaisseService(db)
    return service.lister_caisses()


@router.get("/principale", response_model=CaisseResponse)
def obtenir_caisse_principale(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Obtient la caisse active principale."""
    service = CaisseService(db)
    caisse = service.get_caisse_principale()
    if not caisse:
        raise HTTPException(status_code=404, detail="Aucune caisse active trouvée")
    return caisse


# ═══════════════════════════════════════════════════════════════════════════
# ═══ AJOUT 5.8 — ENDPOINTS MULTI-DEVISES (DÉBUT)                         ═══
# ═══════════════════════════════════════════════════════════════════════════
# ⚠️ Ces routes DOIVENT être déclarées AVANT /{id_caisse}, sinon FastAPI
#    matcherait /caisses/taux comme /caisses/{id_caisse="taux"} → 422.
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/taux", response_model=TauxChangeResponse)
def creer_ou_mettre_a_jour_taux(
    payload: TauxChangeCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """
    Crée ou met à jour un taux de change pour une organisation et une date.

    Réservé aux rôles : ADMIN, DG, CAISSE, COMPTABLE.
    """
    # --- Contrôle d'isolation multi-tenant ---
    if not getattr(current_user, "is_platform_admin", False):
        if payload.organisation_id != current_user.organisation_id:
            raise HTTPException(
                status_code=403,
                detail="Vous ne pouvez gérer que les taux de votre propre organisation.",
            )

    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG", "CAISSE", "COMPTABLE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")

    service = TauxChangeService(db)
    try:
        taux = service.enregistrer_taux(
            organisation_id=payload.organisation_id,
            devise_source=payload.devise_source,
            devise_cible=payload.devise_cible,
            taux=float(payload.taux),
            date_taux=payload.date_taux,
            source=payload.source or "MANUEL",
            user_id=current_user.id,
        )
        db.commit()
        db.refresh(taux)
        return taux
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur interne : {e}")


@router.get("/taux", response_model=List[TauxChangeResponse])
def lister_taux(
    organisation_id: Optional[int] = Query(
        None, description="Requis pour un ADMIN plateforme ; ignoré sinon"
    ),
    devise_source: Optional[str] = Query(None, description="Filtre devise source (ex: USD)"),
    devise_cible: Optional[str] = Query(None, description="Filtre devise cible (ex: CDF)"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """Liste les taux de change de l'organisation."""
    # --- Détermination de l'organisation cible ---
    if getattr(current_user, "is_platform_admin", False):
        if not organisation_id:
            raise HTTPException(
                status_code=400,
                detail="organisation_id est requis pour un ADMIN plateforme.",
            )
        target_org = organisation_id
    else:
        target_org = current_user.organisation_id

    service = TauxChangeService(db)
    return service.lister_taux(
        organisation_id=target_org,
        devise_source=devise_source,
        devise_cible=devise_cible,
        limit=limit,
    )


@router.get("/taux/dernier", response_model=TauxChangeResponse)
def obtenir_dernier_taux(
    devise_source: str = Query(..., min_length=3, max_length=3),
    devise_cible: str = Query(..., min_length=3, max_length=3),
    organisation_id: Optional[int] = Query(
        None, description="Requis pour un ADMIN plateforme ; ignoré sinon"
    ),
    date_reference: Optional[date] = Query(
        None, description="Date de référence (défaut : aujourd'hui)"
    ),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """Retourne le taux le plus récent ≤ date_reference pour le couple de devises."""
    if getattr(current_user, "is_platform_admin", False):
        if not organisation_id:
            raise HTTPException(
                status_code=400,
                detail="organisation_id est requis pour un ADMIN plateforme.",
            )
        target_org = organisation_id
    else:
        target_org = current_user.organisation_id

    service = TauxChangeService(db)
    taux = service.obtenir_taux(
        organisation_id=target_org,
        devise_source=devise_source,
        devise_cible=devise_cible,
        date_reference=date_reference,
    )
    if not taux:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Aucun taux trouvé pour {devise_source.upper()} → {devise_cible.upper()} "
                f"(organisation #{target_org})"
            ),
        )
    return taux


@router.post("/convertir", response_model=ConversionResponse)
def convertir_montant(
    payload: ConversionRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
):
    """Convertit un montant d'une devise vers une autre selon le taux applicable."""
    # --- Contrôle d'isolation multi-tenant ---
    if not getattr(current_user, "is_platform_admin", False):
        if payload.organisation_id != current_user.organisation_id:
            raise HTTPException(
                status_code=403,
                detail="Vous ne pouvez convertir que pour votre propre organisation.",
            )

    service = TauxChangeService(db)
    try:
        return service.convertir(
            organisation_id=payload.organisation_id,
            montant=float(payload.montant),
            devise_source=payload.devise_source,
            devise_cible=payload.devise_cible,
            date_reference=payload.date_reference,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# ═══ AJOUT 5.8 — ENDPOINTS MULTI-DEVISES (FIN)                           ═══
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/{id_caisse}", response_model=CaisseResponse)
def obtenir_caisse(
    id_caisse: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère les détails d'une caisse spécifique."""
    service = CaisseService(db)
    caisse = service.obtenir_caisse(id_caisse)
    if not caisse:
        raise HTTPException(status_code=404, detail="Caisse non trouvée")
    return caisse


@router.post("/", response_model=CaisseResponse)
def creer_caisse(
    data: CaisseCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Création d'une nouvelle caisse (Admin / DG / Caisse)."""
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG", "CAISSE", "COMPTABLE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = CaisseService(db)
    return service.creer_caisse(data)


@router.put("/{id_caisse}", response_model=CaisseResponse)
def mettre_a_jour_caisse(
    id_caisse: int,
    data: CaisseUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Mise à jour des soldes ou du statut d'une caisse."""
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG", "CAISSE", "COMPTABLE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = CaisseService(db)
    caisse = service.mettre_a_jour_caisse(id_caisse, data)
    if not caisse:
        raise HTTPException(status_code=404, detail="Caisse non trouvée")
    return caisse


@router.post("/{id_caisse}/rapprochement", response_model=CaisseResponse)
def effectuer_rapprochement(
    id_caisse: int,
    solde_physique: float = Query(..., ge=0, description="Nouveau solde physique constaté"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Effectue un rapprochement de caisse avec le solde physique constaté."""
    role = current_user.role.nom.upper() if current_user.role else "USER"
    if role not in ["ADMIN", "DG", "CAISSE"]:
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    service = CaisseService(db)
    caisse = service.effectuer_rapprochement(id_caisse, solde_physique)
    if not caisse:
        raise HTTPException(status_code=404, detail="Caisse non trouvée")
    return caisse