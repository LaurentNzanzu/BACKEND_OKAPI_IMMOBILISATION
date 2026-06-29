# backend/app/models/budget.py
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
from ..core.database import Base

class Budget(Base):
    __tablename__ = "budgets"
    
    id_budget = Column(Integer, primary_key=True, index=True)
    centre_cout = Column(String(100), nullable=False, index=True)
    exercice = Column(Integer, nullable=False, index=True)
    montant_alloue = Column(Numeric(15, 2), nullable=False, default=0)
    montant_utilise = Column(Numeric(15, 2), nullable=False, default=0)

    date_creation = Column(DateTime, default=datetime.utcnow)
    date_modification = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    validations = relationship("Validation", back_populates="budget", lazy="select")

    __table_args__ = (
        UniqueConstraint('centre_cout', 'exercice', name='uq_budget_centre_exercice'),
    )

    @property
    def solde_disponible(self) -> Decimal:
        """Calcule le solde disponible du budget."""
        return Decimal(str(self.montant_alloue)) - Decimal(str(self.montant_utilise))

    @property
    def taux_utilisation(self) -> float:
        """Calcule le taux d'utilisation du budget en pourcentage."""
        if self.montant_alloue == 0:
            return 0.0
        return float(Decimal(str(self.montant_utilise)) / Decimal(str(self.montant_alloue)) * 100)

    def peut_engager(self, montant: float) -> bool:
        """
        Vérifie si le budget peut engager un montant donné.
        
        Le montant doit être strictement positif et le solde disponible doit être suffisant.
        
        Args:
            montant (float): Le montant à engager.
            
        Returns:
            bool: True si l'engagement est possible, False sinon.
        """
        if montant <= 0:
            return False
        return float(self.solde_disponible) >= montant

    def engager(self, montant: float):
        """
        Engage un montant sur le budget.
        
        Args:
            montant (float): Le montant à engager.
            
        Raises:
            ValueError: Si le montant est inférieur ou égal à zéro.
            ValueError: Si le budget est insuffisant pour le montant demandé.
        """
        # Règle 1 : Le montant doit être strictement positif
        if montant <= 0:
            raise ValueError("Le montant à engager doit être strictement positif.")
            
        # Règle 2 : Le budget doit disposer d'un solde suffisant
        if not self.peut_engager(montant):
            raise ValueError(
                f"Budget insuffisant pour le centre de coût '{self.centre_cout}' "
                f"(exercice {self.exercice}). Solde disponible: {self.solde_disponible}, "
                f"Montant demandé: {montant}"
            )
            
        # Mise à jour de l'attribut (Aucun commit ici, géré par la couche service)
        self.montant_utilise = Decimal(str(self.montant_utilise)) + Decimal(str(montant))

    def desengager(self, montant: float):
        """
        Désengage un montant du budget.
        
        Args:
            montant (float): Le montant à désengager.
            
        Raises:
            ValueError: Si le montant à désengager est supérieur au montant utilisé.
        """
        if montant > float(self.montant_utilise):
            raise ValueError(
                f"Impossible de désengager {montant} car le montant utilisé "
                f"({self.montant_utilise}) est inférieur"
            )
        self.montant_utilise = Decimal(str(self.montant_utilise)) - Decimal(str(montant))