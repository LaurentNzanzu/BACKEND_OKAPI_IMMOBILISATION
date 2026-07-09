# backend/app/models/validation.py
import enum
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum as SQLEnum, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base

class OrdreValidation(enum.Enum):
    TECHNICIEN = "TECHNICIEN"
    COMPTABLE = "COMPTABLE"
    CAISSE = "CAISSE"
    DG = "DG"

class DecisionValidation(enum.Enum):
    APPROUVE = "APPROUVE"
    REJETE = "REJETE"
    EN_ATTENTE = "EN_ATTENTE"

class TypeValidation(enum.Enum):
    BESOIN = "BESOIN"
    DEPRECIATION = "DEPRECIATION"
    CESSION = "CESSION"
    AMORTISSEMENT = "AMORTISSEMENT"

# Ordre strict du workflow
WORKFLOW_ORDER = [
    OrdreValidation.COMPTABLE,
    OrdreValidation.CAISSE,
    OrdreValidation.DG
]

class Validation(Base):
    __tablename__ = "validations"
    
    id_validation = Column(Integer, primary_key=True, index=True)

    # Clés étrangères
    id_besoin = Column(Integer, ForeignKey("besoins.id_besoin", ondelete="CASCADE"), nullable=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=True)
    id_budget = Column(Integer, ForeignKey("budgets.id_budget", ondelete="SET NULL"), nullable=True)
    id_validateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)

    # Informations de validation
    ordre_validateur = Column(SQLEnum(OrdreValidation), nullable=False)
    type_validation = Column(SQLEnum(TypeValidation), nullable=False, default=TypeValidation.BESOIN)
    decision = Column(SQLEnum(DecisionValidation), default=DecisionValidation.EN_ATTENTE)

    # Champs obligatoires en cas de rejet
    motif_rejet = Column(Text, nullable=True)
    piece_justificative_url = Column(String(500), nullable=True)

    # Montant engagé
    montant_engage = Column(Numeric(15, 2), nullable=True)

    # Dates
    date_validation = Column(DateTime, default=datetime.utcnow)
    date_decision = Column(DateTime, nullable=True)
    commentaire = Column(Text, nullable=True)

    # Relations
    besoin = relationship("Besoin", back_populates="validations")
    bien = relationship("Bien", back_populates="validations")
    budget = relationship("Budget", back_populates="validations")
    validateur = relationship("Utilisateur", foreign_keys=[id_validateur])

    # Écritures comptables liées
    ecritures_comptables = relationship(
        "EcritureComptable",
        back_populates="validation",
        lazy="select"
    )

    # =========================================================================
    # MÉTHODES MÉTIER INTERNES
    # =========================================================================

    def _get_entity_validations(self):
        """Récupère la liste des validations associées à la même entité (Besoin ou Bien)."""
        if self.id_besoin and self.besoin:
            return self.besoin.validations
        if self.id_bien and self.bien:
            return self.bien.validations
        return []

    def est_rejete(self) -> bool:
        """
        Vérifie si le workflow a été rejeté à n'importe quelle étape.
        
        Returns:
            bool: True si une validation a été rejetée, False sinon.
        """
        validations = self._get_entity_validations()
        return any(v.decision == DecisionValidation.REJETE for v in validations)

    # =========================================================================
    # MÉTHODES MÉTIER PUBLIQUES (WORKFLOW)
    # =========================================================================

    def deja_valide_par(self, role: OrdreValidation) -> bool:
        """
        Vérifie si un rôle spécifique a déjà approuvé la validation pour cette entité.
        
        Args:
            role (OrdreValidation): Le rôle à vérifier.
            
        Returns:
            bool: True si le rôle a déjà approuvé, False sinon.
        """
        validations = self._get_entity_validations()
        return any(
            v.ordre_validateur == role and v.decision == DecisionValidation.APPROUVE 
            for v in validations
        )

    def prochain_validateur(self) -> OrdreValidation:
        """
        Détermine le prochain rôle attendu dans le workflow.
        
        Returns:
            OrdreValidation: Le prochain rôle à valider, ou None si le workflow est terminé.
        """
        if self.est_rejete():
            return None  # Workflow terminé par rejet
            
        for role in WORKFLOW_ORDER:
            if not self.deja_valide_par(role):
                return role
                
        return None  # Workflow terminé (tous les rôles ont validé)

    def peut_valider(self) -> bool:
        """
        Vérifie si la validation actuelle est autorisée à être traitée.
        Cela signifie que son rôle est le prochain attendu et que le workflow n'est pas bloqué.
        
        Returns:
            bool: True si cette validation peut être traitée, False sinon.
        """
        if self.est_rejete():
            return False
            
        if self.decision != DecisionValidation.EN_ATTENTE:
            return False  # Déjà traitée
            
        prochain = self.prochain_validateur()
        return prochain == self.ordre_validateur

    def est_terminee(self) -> bool:
        """
        Vérifie si le workflow est entièrement terminé.
        Le workflow est terminé si le DG a validé OU si une validation a été rejetée.
        
        Returns:
            bool: True si le workflow est terminé, False sinon.
        """
        if self.est_rejete():
            return True
        return self.deja_valide_par(OrdreValidation.DG)

    @property
    def workflow_termine(self) -> bool:
        """Propriété alias pour est_terminee(), conforme aux exigences du cahier des charges."""
        return self.est_terminee()

    def approuver(self):
        """
        Approuve la validation actuelle.
        
        Raises:
            ValueError: Si la validation ne peut pas être traitée (rôle non attendu ou workflow bloqué).
        """
        if not self.peut_valider():
            raise ValueError(
                f"Impossible d'approuver : le rôle '{self.ordre_validateur.value}' "
                f"n'est pas le prochain attendu dans le workflow ou le workflow est déjà terminé/bloqué."
            )
        
        self.decision = DecisionValidation.APPROUVE
        self.date_decision = datetime.utcnow()

    def rejeter(self, motif_rejet: str):
        """
        Rejette la validation actuelle et stoppe définitivement le workflow.
        
        Args:
            motif_rejet (str): Le motif du rejet (obligatoire).
            
        Raises:
            ValueError: Si la validation ne peut pas être traitée ou si le motif est vide.
        """
        if not self.peut_valider():
            raise ValueError(
                f"Impossible de rejeter : le rôle '{self.ordre_validateur.value}' "
                f"n'est pas le prochain attendu dans le workflow ou le workflow est déjà terminé/bloqué."
            )
            
        if not motif_rejet or not motif_rejet.strip():
            raise ValueError("Un motif de rejet est obligatoire.")
            
        self.decision = DecisionValidation.REJETE
        self.motif_rejet = motif_rejet.strip()
        self.date_decision = datetime.utcnow()

    # =========================================================================
    # COMPATIBILITÉ (MÉTHODES LEGACY)
    # =========================================================================

    def valider(self, decision: DecisionValidation, motif_rejet: str = None):
        """
        Méthode legacy pour valider ou rejeter. Redirige vers approuver() ou rejeter().
        """
        if decision == DecisionValidation.APPROUVE:
            self.approuver()
        elif decision == DecisionValidation.REJETE:
            self.rejeter(motif_rejet or "")
        else:
            raise ValueError("Décision non valide.")
        return self

    def est_approuvee(self) -> bool:
        """Vérifie si la validation courante (et non le workflow entier) est approuvée."""
        return self.decision == DecisionValidation.APPROUVE