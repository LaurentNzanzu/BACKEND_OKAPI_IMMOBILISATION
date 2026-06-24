from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum

class StatutBesoin(enum.Enum):
    BROUILLON = "BROUILLON"
    EN_VALIDATION = "EN_VALIDATION"
    DG_VALIDE = "DG_VALIDE"
    COMPTABLE_VALIDE = "COMPTABLE_VALIDE"
    CAISSE_VALIDE = "CAISSE_VALIDE"
    REJETE = "REJETE"
    APPROUVEE = "APPROUVEE"
    ATTENTE_STOCK = "ATTENTE_STOCK"

class Besoin(Base):
    __tablename__ = "besoins"

    id_besoin = Column(Integer, primary_key=True, index=True)
    id_panne = Column(Integer, ForeignKey("pannes.id_panne", ondelete="CASCADE"), nullable=False)
    numero_demande = Column(String(50), unique=True, nullable=False)
    date_creation = Column(DateTime, default=datetime.utcnow)
    montant_total = Column(Float, default=0.0)
    statut = Column(SQLEnum(StatutBesoin), default=StatutBesoin.BROUILLON)
    observations = Column(String, nullable=True)

    # Relations
    panne = relationship("Panne", back_populates="besoins")
    lignes = relationship("LigneBesoin", back_populates="besoin", cascade="all, delete-orphan")
    validations = relationship("Validation", back_populates="besoin", cascade="all, delete-orphan")
    fournitures = relationship("FourniturePiece", back_populates="besoin", cascade="all, delete-orphan")

    def calculer_montant_total(self) -> float:
        """Recalcule le montant total à partir des lignes"""
        total = sum(ligne.prix_total for ligne in self.lignes)
        self.montant_total = total
        return total

    def peut_etre_validee(self, role: str) -> bool:
        """Vérifie si le rôle actuel est autorisé à valider l'étape"""
        # DG valide quand c'est BROUILLON
        if self.statut == StatutBesoin.BROUILLON and role == "DG":
            return True
        # Comptable valide quand DG a validé
        if self.statut == StatutBesoin.DG_VALIDE and role == "COMPTABLE":
            return True
        # Caisse valide quand Comptable a validé
        if self.statut == StatutBesoin.COMPTABLE_VALIDE and role == "CAISSE":
            return True
        return False

    def passer_validation_suivante(self) -> bool:
        """Passe au statut suivant après une validation réussie"""
        # Après DG -> DG_VALIDE
        if self.statut == StatutBesoin.BROUILLON:
            self.statut = StatutBesoin.DG_VALIDE
            return True
        # Après Comptable -> COMPTABLE_VALIDE
        if self.statut == StatutBesoin.DG_VALIDE:
            self.statut = StatutBesoin.COMPTABLE_VALIDE
            return True
        # Après Caisse -> CAISSE_VALIDE (Le service passera ensuite à APPROUVEE)
        if self.statut == StatutBesoin.COMPTABLE_VALIDE:
            self.statut = StatutBesoin.CAISSE_VALIDE
            return True
        return False