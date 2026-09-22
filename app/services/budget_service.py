# backend/app/services/budget_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict
from decimal import Decimal
from datetime import datetime
import logging

from ..models.budget import Budget
from ..models.validation import Validation, DecisionValidation
from ..schemas.budget import BudgetCreate, BudgetUpdate, BudgetVerification

logger = logging.getLogger(__name__)

class BudgetService:
    def __init__(self, db: Session):
        self.db = db

    # ═══ 5.22 — Filtre organisation_id ═══
    def get_budget(self, centre_cout: str, exercice: int, organisation_id: Optional[int] = None) -> Optional[Budget]:
        """Récupère un budget par centre de coût et exercice (scopé par ONG si fourni)."""
        query = self.db.query(Budget).filter(
            Budget.centre_cout == centre_cout,
            Budget.exercice == exercice
        )
        if organisation_id is not None:
            query = query.filter(Budget.organisation_id == organisation_id)
        return query.first()

    def get_or_create_budget(self, centre_cout: str, exercice: int, montant_alloue: Decimal = Decimal('0'), organisation_id: Optional[int] = None) -> Budget:
        """Récupère ou crée un budget."""
        budget = self.get_budget(centre_cout, exercice, organisation_id=organisation_id)
        if not budget:
            budget = Budget(
                centre_cout=centre_cout,
                exercice=exercice,
                montant_alloue=montant_alloue,
                montant_utilise=Decimal('0'),
                organisation_id=organisation_id,   # ═══ 5.22 ═══
            )
            self.db.add(budget)
            self.db.flush()
        return budget

    def verifier_disponibilite(self, centre_cout: str, exercice: int, montant: Decimal, organisation_id: Optional[int] = None):
        """Vérifie si le budget est suffisant pour un montant donné (Règle d'or)."""
        from ..schemas.budget import BudgetVerification
        
        budget = self.get_budget(centre_cout, exercice, organisation_id=organisation_id)
        
        if not budget:
            return BudgetVerification(
                est_disponible=False,
                solde_disponible=Decimal('0'),
                montant_demande=montant,
                message=f"Aucun budget trouvé pour le centre de coût '{centre_cout}' en {exercice}"
            )
        
        solde = budget.solde_disponible
        
        if solde >= montant:
            return BudgetVerification(
                est_disponible=True,
                solde_disponible=solde,
                montant_demande=montant,
                message="Budget suffisant"
            )
        else:
            return BudgetVerification(
                est_disponible=False,
                solde_disponible=solde,
                montant_demande=montant,
                message=f"Budget insuffisant. Solde disponible: {solde}, Montant demandé: {montant}"
            )

    def engager_montant(self, centre_cout: str, exercice: int, montant: Decimal, validation_id: int = None, organisation_id: Optional[int] = None) -> Budget:
        """Engage un montant sur le budget (débit)."""
        budget = self.get_budget(centre_cout, exercice, organisation_id=organisation_id)
        if not budget:
            raise ValueError(f"Budget non trouvé pour {centre_cout} en {exercice}")
        
        verification = self.verifier_disponibilite(centre_cout, exercice, montant, organisation_id=organisation_id)
        if not verification.est_disponible:
            raise ValueError(verification.message)
        
        budget.engager(float(montant))
        budget.date_modification = datetime.utcnow()
        
        if validation_id:
            validation = self.db.query(Validation).filter(
                Validation.id_validation == validation_id
            ).first()
            if validation:
                validation.montant_engage = montant
        
        return budget

    def desengager_montant(self, centre_cout: str, exercice: int, montant: Decimal, organisation_id: Optional[int] = None) -> Budget:
        """Désengage un montant du budget (annulation)."""
        budget = self.get_budget(centre_cout, exercice, organisation_id=organisation_id)
        if not budget:
            raise ValueError(f"Budget non trouvé pour {centre_cout} en {exercice}")
        
        budget.desengager(float(montant))
        budget.date_modification = datetime.utcnow()
        
        return budget

    def get_solde_par_centre(self, centre_cout: str, exercice: int, organisation_id: Optional[int] = None) -> Dict:
        """Retourne le solde d'un centre de coût."""
        budget = self.get_budget(centre_cout, exercice, organisation_id=organisation_id)
        if not budget:
            return {
                "centre_cout": centre_cout,
                "exercice": exercice,
                "montant_alloue": Decimal('0'),
                "montant_utilise": Decimal('0'),
                "solde_disponible": Decimal('0'),
                "taux_utilisation": 0.0
            }
        
        return {
            "centre_cout": budget.centre_cout,
            "exercice": budget.exercice,
            "montant_alloue": budget.montant_alloue,
            "montant_utilise": budget.montant_utilise,
            "solde_disponible": budget.solde_disponible,
            "taux_utilisation": budget.taux_utilisation
        }

    def get_synthese_budgetaire(self, exercice: int, organisation_id: Optional[int] = None) -> Dict:
        """Retourne une synthèse de tous les budgets pour un exercice."""
        query = self.db.query(Budget).filter(Budget.exercice == exercice)
        if organisation_id is not None:
            query = query.filter(Budget.organisation_id == organisation_id)
        budgets = query.all()
        
        total_alloue = Decimal('0')
        total_utilise = Decimal('0')
        
        details = []
        for budget in budgets:
            total_alloue += budget.montant_alloue
            total_utilise += budget.montant_utilise
            details.append({
                "centre_cout": budget.centre_cout,
                "montant_alloue": budget.montant_alloue,
                "montant_utilise": budget.montant_utilise,
                "solde": budget.solde_disponible,
                "taux_utilisation": budget.taux_utilisation
            })
        
        return {
            "exercice": exercice,
            "total_alloue": total_alloue,
            "total_utilise": total_utilise,
            "total_disponible": total_alloue - total_utilise,
            "taux_global_utilisation": float(total_utilise / total_alloue * 100) if total_alloue > 0 else 0,
            "details": details,
            "nombre_budgets": len(budgets)
        }

    def creer_budget(self, data, organisation_id: Optional[int] = None) -> Budget:
        """Crée un nouveau budget."""
        existing = self.get_budget(data.centre_cout, data.exercice, organisation_id=organisation_id)
        if existing:
            raise ValueError(f"Un budget existe déjà pour {data.centre_cout} en {data.exercice}")
        
        budget = Budget(
            centre_cout=data.centre_cout,
            exercice=data.exercice,
            montant_alloue=data.montant_alloue,
            montant_utilise=Decimal('0'),
            organisation_id=organisation_id,   # ═══ 5.22 ═══
        )
        self.db.add(budget)
        return budget

    def update_budget(self, id_budget: int, data, organisation_id: Optional[int] = None) -> Budget:
        """Met à jour un budget."""
        query = self.db.query(Budget).filter(Budget.id_budget == id_budget)
        if organisation_id is not None:
            query = query.filter(Budget.organisation_id == organisation_id)
        budget = query.first()
        if not budget:
            raise ValueError("Budget non trouvé")
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(budget, field, value)
        
        budget.date_modification = datetime.utcnow()
        return budget

    def verifier_tresorerie(self, montant: Decimal, organisation_id: Optional[int] = None) -> Dict:
        """
        Vérifie si la trésorerie est suffisante pour un montant donné.
        Interroge dynamiquement CaisseService.verifier_tresorerie().
        """
        from .caisse_service import CaisseService
        caisse_service = CaisseService(self.db)
        res = caisse_service.verifier_tresorerie(float(montant), organisation_id=organisation_id)
        return {
            "est_suffisante": res["est_suffisante"],
            "tresorerie_disponible": Decimal(str(res["solde_disponible"])),
            "montant_demande": montant,
            "manque": max(Decimal('0'), montant - Decimal(str(res["solde_disponible"])))
        }
    # ═══ FIN 5.22 ═══