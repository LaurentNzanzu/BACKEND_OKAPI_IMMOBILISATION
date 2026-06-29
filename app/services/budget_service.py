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

    def get_budget(self, centre_cout: str, exercice: int) -> Optional[Budget]:
        """Récupère un budget par centre de coût et exercice"""
        return self.db.query(Budget).filter(
            Budget.centre_cout == centre_cout,
            Budget.exercice == exercice
        ).first()

    def get_or_create_budget(self, centre_cout: str, exercice: int, montant_alloue: Decimal = Decimal('0')) -> Budget:
        """Récupère ou crée un budget"""
        budget = self.get_budget(centre_cout, exercice)
        if not budget:
            budget = Budget(
                centre_cout=centre_cout,
                exercice=exercice,
                montant_alloue=montant_alloue,
                montant_utilise=Decimal('0')
            )
            self.db.add(budget)
            self.db.flush()
        return budget

    def verifier_disponibilite(self, centre_cout: str, exercice: int, montant: Decimal):
        """Vérifie si le budget est suffisant pour un montant donné (Règle d'or)"""
        from ..schemas.budget import BudgetVerification
        
        budget = self.get_budget(centre_cout, exercice)
        
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

    def engager_montant(self, centre_cout: str, exercice: int, montant: Decimal, validation_id: int = None) -> Budget:
        """Engage un montant sur le budget (débit)"""
        budget = self.get_budget(centre_cout, exercice)
        if not budget:
            raise ValueError(f"Budget non trouvé pour {centre_cout} en {exercice}")
        
        # Vérifier la disponibilité
        verification = self.verifier_disponibilite(centre_cout, exercice, montant)
        if not verification.est_disponible:
            raise ValueError(verification.message)
        
        # Engager le montant
        budget.engager(float(montant))
        budget.date_modification = datetime.utcnow()
        
        # Si une validation est associée, mettre à jour le montant engagé
        if validation_id:
            validation = self.db.query(Validation).filter(
                Validation.id_validation == validation_id
            ).first()
            if validation:
                validation.montant_engage = montant
        
        return budget

    def desengager_montant(self, centre_cout: str, exercice: int, montant: Decimal) -> Budget:
        """Désengage un montant du budget (annulation)"""
        budget = self.get_budget(centre_cout, exercice)
        if not budget:
            raise ValueError(f"Budget non trouvé pour {centre_cout} en {exercice}")
        
        budget.desengager(float(montant))
        budget.date_modification = datetime.utcnow()
        
        return budget

    def get_solde_par_centre(self, centre_cout: str, exercice: int) -> Dict:
        """Retourne le solde d'un centre de coût"""
        budget = self.get_budget(centre_cout, exercice)
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

    def get_synthese_budgetaire(self, exercice: int) -> Dict:
        """Retourne une synthèse de tous les budgets pour un exercice"""
        budgets = self.db.query(Budget).filter(Budget.exercice == exercice).all()
        
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

    def creer_budget(self, data) -> Budget:
        """Crée un nouveau budget"""
        # Vérifier si un budget existe déjà
        existing = self.get_budget(data.centre_cout, data.exercice)
        if existing:
            raise ValueError(f"Un budget existe déjà pour {data.centre_cout} en {data.exercice}")
        
        budget = Budget(
            centre_cout=data.centre_cout,
            exercice=data.exercice,
            montant_alloue=data.montant_alloue,
            montant_utilise=Decimal('0')
        )
        self.db.add(budget)
        # ✅ Le commit est géré par l'appelant (with db.begin())
        return budget

    def update_budget(self, id_budget: int, data) -> Budget:
        """Met à jour un budget"""
        budget = self.db.query(Budget).filter(Budget.id_budget == id_budget).first()
        if not budget:
            raise ValueError("Budget non trouvé")
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(budget, field, value)
        
        budget.date_modification = datetime.utcnow()
        # ✅ Le commit est géré par l'appelant (with db.begin())
        return budget

    def verifier_tresorerie(self, montant: Decimal) -> Dict:
        """
        Vérifie si la trésorerie est suffisante pour un montant donné.
        Cette méthode sera implémentée avec la vraie logique de trésorerie.
        """
        # TODO: Implémenter la vraie vérification de trésorerie
        tresorerie_disponible = Decimal('1000000')
        
        return {
            "est_suffisante": tresorerie_disponible >= montant,
            "tresorerie_disponible": tresorerie_disponible,
            "montant_demande": montant,
            "manque": max(Decimal('0'), montant - tresorerie_disponible)
        }