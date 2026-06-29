# backend/app/api/endpoints/caisse.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.caisse import CaisseCreate, CaisseUpdate, CaisseResponse, TresorerieVerificationResponse
from ...services.caisse_service import CaisseService

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
