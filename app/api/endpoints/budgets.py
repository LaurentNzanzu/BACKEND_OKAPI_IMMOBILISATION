# backend/app/api/endpoints/budgets.py
import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
from decimal import Decimal

from ...models.budget import Budget
from ...models.validation import DecisionValidation, Validation
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.utilisateur import Utilisateur
from ...schemas.budget import (
    BudgetCreate, BudgetUpdate, BudgetResponse, 
    BudgetDetailResponse, BudgetVerification, BudgetConsommation,
    BudgetSummary
)
from ...schemas.reponse import ReponseStandard
from ...services.budget_service import BudgetService
from ...services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/budgets", tags=["Budgets"])


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def check_budget_permission(user: Utilisateur, action: str = "view") -> bool:
    """Vérifie les permissions sur les budgets."""
    if not user:
        return False
    role = user.role.nom.upper() if user.role else "USER"
    if role in ["ADMIN", "DG", "COMPTABLE"]:
        return True
    if role == "CAISSE" and action in ["view"]:
        return True
    return False


# ============================================================
# ENDPOINTS CRUD (AVEC TRANSACTIONS ACID)
# ============================================================

@router.post("/", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    data: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """Crée un nouveau budget."""
    if not check_budget_permission(current_user, "create"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = BudgetService(db)
    audit_service = AuditService(db)
    
    try:
        # ✅ with db.begin() gère automatiquement le commit/rollback
        with db.begin():
            budget = service.creer_budget(data)
            
            audit_service.log_create(
                user_id=current_user.id,
                table_name="budgets",
                record_id=budget.id_budget,
                new_values={
                    "centre_cout": budget.centre_cout,
                    "exercice": budget.exercice,
                    "montant_alloue": float(budget.montant_alloue)
                },
                request=request
            )
            
        # ✅ Rafraîchir après le commit
        db.refresh(budget)
        return budget
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD création budget: {e}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")


@router.get("/", response_model=List[BudgetResponse])
async def get_budgets(
    exercice: Optional[int] = Query(None, description="Filtrer par exercice"),
    centre_cout: Optional[str] = Query(None, description="Filtrer par centre de coût"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère la liste des budgets."""
    if not check_budget_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    query = db.query(Budget)
    
    if exercice:
        query = query.filter(Budget.exercice == exercice)
    if centre_cout:
        query = query.filter(Budget.centre_cout.ilike(f"%{centre_cout}%"))
    
    budgets = query.offset(skip).limit(limit).all()
    return budgets


@router.get("/{id_budget}", response_model=BudgetDetailResponse)
async def get_budget(
    id_budget: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère un budget avec ses détails."""
    if not check_budget_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    budget = db.query(Budget).filter(Budget.id_budget == id_budget).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget non trouvé")
    
    return BudgetDetailResponse.from_budget(budget)


@router.put("/{id_budget}", response_model=BudgetResponse)
async def update_budget(
    id_budget: int,
    data: BudgetUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """Met à jour un budget."""
    if not check_budget_permission(current_user, "edit"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = BudgetService(db)
    audit_service = AuditService(db)
    
    old_budget = db.query(Budget).filter(Budget.id_budget == id_budget).first()
    if not old_budget:
        raise HTTPException(status_code=404, detail="Budget non trouvé")
    
    try:
        # ✅ with db.begin() gère automatiquement le commit/rollback
        with db.begin():
            budget = service.update_budget(id_budget, data)
            
            audit_service.log_update(
                user_id=current_user.id,
                table_name="budgets",
                record_id=id_budget,
                old_values={
                    "montant_alloue": float(old_budget.montant_alloue),
                    "montant_utilise": float(old_budget.montant_utilise)
                },
                new_values={
                    "montant_alloue": float(budget.montant_alloue),
                    "montant_utilise": float(budget.montant_utilise)
                },
                request=request
            )
            
        db.refresh(budget)
        return budget
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD mise à jour budget {id_budget}: {e}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")


@router.delete("/{id_budget}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    id_budget: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user),
    request: Request = None
):
    """Supprime un budget."""
    if not check_budget_permission(current_user, "delete"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    budget = db.query(Budget).filter(Budget.id_budget == id_budget).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget non trouvé")
    
    try:
        # ✅ with db.begin() pour la suppression
        with db.begin():
            audit_service = AuditService(db)
            audit_service.log_delete(
                user_id=current_user.id,
                table_name="budgets",
                record_id=id_budget,
                old_values={
                    "centre_cout": budget.centre_cout,
                    "exercice": budget.exercice,
                    "montant_alloue": float(budget.montant_alloue)
                },
                request=request
            )
            db.delete(budget)
            
    except SQLAlchemyError as e:
        logger.error(f"Erreur BDD suppression budget {id_budget}: {e}")
        raise HTTPException(status_code=503, detail="Erreur de base de données")


# ============================================================
# ENDPOINTS DE CONSULTATION (LECTURE RAPIDE)
# ============================================================

@router.get("/verification", response_model=BudgetVerification)
async def verifier_disponibilite(
    centre_cout: str = Query(..., description="Centre de coût"),
    exercice: int = Query(..., description="Exercice comptable"),
    montant: Decimal = Query(..., gt=0, description="Montant à vérifier (strictement positif)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Vérifie la disponibilité budgétaire (Règle d'or).
    Lecture seule, pas de transaction nécessaire.
    """
    if not check_budget_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    if montant <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit être strictement positif")
    
    service = BudgetService(db)
    return service.verifier_disponibilite(centre_cout, exercice, montant)


@router.get("/consommation/{centre_cout}", response_model=BudgetConsommation)
async def get_consommation_budget(
    centre_cout: str,
    exercice: Optional[int] = Query(None, description="Exercice comptable"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère la consommation d'un centre de coût."""
    if not check_budget_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = BudgetService(db)
    
    if not exercice:
        exercice = datetime.datetime.utcnow().year
    
    budget = service.get_budget(centre_cout, exercice)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget non trouvé")
    
    engagements = db.query(Validation).filter(
        Validation.id_budget == budget.id_budget,
        Validation.decision == DecisionValidation.APPROUVE
    ).all()
    
    return BudgetConsommation(
        id_budget=budget.id_budget,
        centre_cout=budget.centre_cout,
        exercice=budget.exercice,
        montant_alloue=budget.montant_alloue,
        montant_utilise=budget.montant_utilise,
        solde_disponible=budget.solde_disponible,
        taux_utilisation=budget.taux_utilisation,
        montants_engages=[
            {
                "validation_id": v.id_validation,
                "montant": float(v.montant_engage) if v.montant_engage else 0,
                "date": v.date_validation.isoformat() if v.date_validation else None
            }
            for v in engagements
        ]
    )


@router.get("/synthese/{exercice}", response_model=BudgetSummary)
async def get_synthese_budgetaire(
    exercice: int,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Récupère la synthèse de tous les budgets pour un exercice."""
    if not check_budget_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    service = BudgetService(db)
    return service.get_synthese_budgetaire(exercice)


@router.get("/tresorerie/verification")
async def verifier_tresorerie(
    montant: Decimal = Query(..., gt=0, description="Montant à vérifier (strictement positif)"),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    """Vérifie la disponibilité de trésorerie."""
    if not check_budget_permission(current_user, "view"):
        raise HTTPException(status_code=403, detail="Permissions insuffisantes")
    
    if montant <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit être strictement positif")
    
    service = BudgetService(db)
    return service.verifier_tresorerie(montant)