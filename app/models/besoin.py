# backend/app/models/besoin.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Boolean, UniqueConstraint
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

    # ═══ 5.22 — Multi-tenant ═══
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Multi-tenant : ONG propriétaire"
    )
    # ═══ FIN 5.22 ═══

    id_panne = Column(Integer, ForeignKey("pannes.id_panne", ondelete="CASCADE"), nullable=False)
    numero_demande = Column(String(50), nullable=False)   # ═══ 5.22 — unique retiré, géré par contrainte composite ═══
    date_creation = Column(DateTime, default=datetime.utcnow)
    montant_total = Column(Float, default=0.0)
    statut = Column(SQLEnum(StatutBesoin), default=StatutBesoin.BROUILLON)
    id_budget = Column(Integer, ForeignKey("budgets.id_budget", ondelete="SET NULL"), nullable=True)
    centre_cout = Column(String(100), nullable=True, index=True)

    # === Projet (Sprint 0) ===
    id_projet = Column(
        Integer,
        ForeignKey("projets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Projet bailleur associé (Sprint 0)"
    )

    # Relations
    organisation = relationship("Organisation")   # ═══ 5.22 ═══
    panne = relationship("Panne", back_populates="besoins")
    projet = relationship("Projet")
    budget = relationship("Budget", foreign_keys=[id_budget])
    lignes = relationship("LigneBesoin", back_populates="besoin", cascade="all, delete-orphan")
    validations = relationship("Validation", back_populates="besoin", cascade="all, delete-orphan")
    fournitures = relationship("FourniturePiece", back_populates="besoin", cascade="all, delete-orphan")

    # ═══ 5.22 — Contrainte UNIQUE scopée par ONG ═══
    __table_args__ = (
        UniqueConstraint('organisation_id', 'numero_demande', name='uq_besoin_org_numero_demande'),
    )
    # ═══ FIN 5.22 ═══

    def calculer_montant_total(self) -> float:
        """Recalcule le montant total à partir des lignes"""
        total = sum(ligne.prix_total for ligne in self.lignes)
        self.montant_total = total
        return total

    def peut_etre_validee(self, role: str) -> bool:
        """Vérifie si le rôle actuel est autorisé à valider l'étape"""
        if self.statut == StatutBesoin.BROUILLON and role == "DG":
            return True
        if self.statut == StatutBesoin.DG_VALIDE and role == "COMPTABLE":
            return True
        if self.statut == StatutBesoin.COMPTABLE_VALIDE and role == "CAISSE":
            return True
        return False

    def passer_validation_suivante(self) -> bool:
        """Passe au statut suivant après une validation réussie"""
        if self.statut == StatutBesoin.BROUILLON:
            self.statut = StatutBesoin.DG_VALIDE
            return True
        if self.statut == StatutBesoin.DG_VALIDE:
            self.statut = StatutBesoin.COMPTABLE_VALIDE
            return True
        if self.statut == StatutBesoin.COMPTABLE_VALIDE:
            self.statut = StatutBesoin.CAISSE_VALIDE
            return True
        return False