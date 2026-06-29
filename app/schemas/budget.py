# app/schemas/budget.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime
from decimal import Decimal


class BudgetBase(BaseModel):
    centre_cout: str = Field(..., min_length=1, max_length=100, description="Service/Département")
    exercice: int = Field(..., ge=2000, le=2100, description="Année comptable")
    montant_alloue: Decimal = Field(..., gt=0, description="Montant total alloué (strictement positif)")
    montant_utilise: Decimal = Field(default=0, ge=0, description="Montant déjà utilisé/engagé")

    @field_validator('montant_utilise')
    @classmethod
    def validate_montant_utilise(cls, v, info):
        montant_alloue = info.data.get('montant_alloue')
        if montant_alloue is not None and v > montant_alloue:
            raise ValueError("Le montant utilisé ne peut pas dépasser le montant alloué")
        return v


class BudgetCreate(BudgetBase):
    """Schéma pour la création d'un budget."""
    pass


class BudgetUpdate(BaseModel):
    """Schéma pour la mise à jour d'un budget."""
    centre_cout: Optional[str] = Field(None, min_length=1, max_length=100)
    exercice: Optional[int] = Field(None, ge=2000, le=2100)
    montant_alloue: Optional[Decimal] = Field(None, gt=0)
    montant_utilise: Optional[Decimal] = Field(None, ge=0)


class BudgetResponse(BaseModel):
    """Schéma de réponse pour un budget."""
    id_budget: int
    centre_cout: str
    exercice: int
    montant_alloue: Decimal
    montant_utilise: Decimal
    date_creation: datetime
    date_modification: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class BudgetDetailResponse(BudgetResponse):
    """Schéma détaillé avec calculs supplémentaires."""
    solde_disponible: Decimal
    taux_utilisation: float
    est_suffisant: bool
    
    @classmethod
    def from_budget(cls, budget):
        """Crée une instance à partir d'un modèle Budget."""
        return cls(
            id_budget=budget.id_budget,
            centre_cout=budget.centre_cout,
            exercice=budget.exercice,
            montant_alloue=budget.montant_alloue,
            montant_utilise=budget.montant_utilise,
            date_creation=budget.date_creation,
            date_modification=budget.date_modification,
            solde_disponible=budget.solde_disponible,
            taux_utilisation=budget.taux_utilisation,
            est_suffisant=budget.peut_engager(0)
        )


class BudgetConsommation(BaseModel):
    """Schéma pour la consommation budgétaire."""
    id_budget: int
    centre_cout: str
    exercice: int
    montant_alloue: Decimal
    montant_utilise: Decimal
    solde_disponible: Decimal
    taux_utilisation: float
    montants_engages: list[dict] = Field(default_factory=list, description="Détail des engagements")


class BudgetVerification(BaseModel):
    """Schéma pour vérifier la disponibilité budgétaire."""
    est_disponible: bool
    solde_disponible: Decimal
    montant_demande: Decimal
    message: Optional[str] = None


class BudgetSummary(BaseModel):
    """Résumé des budgets par exercice."""
    exercice: int
    total_alloue: Decimal
    total_utilise: Decimal
    total_disponible: Decimal
    nombre_budgets: int
    taux_global_utilisation: float