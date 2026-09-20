# app/models/abonnement_facturation.py
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Numeric, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class StatutPaiement(str, enum.Enum):
    EN_ATTENTE = "EN_ATTENTE"
    PAYE = "PAYE"
    RETARD = "RETARD"


class AbonnementFacturation(Base):
    __tablename__ = "abonnements_facturation"

    id = Column(Integer, primary_key=True, index=True)
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    periode = Column(String(20), nullable=False, comment="Ex: 2026-01, 2026-Q1")
    montant = Column(Numeric(12, 2), nullable=False)
    devise = Column(String(3), default="USD", nullable=False)
    statut_paiement = Column(SQLEnum(StatutPaiement), default=StatutPaiement.EN_ATTENTE, nullable=False)
    date_echeance = Column(Date, nullable=True)
    date_paiement = Column(DateTime, nullable=True)
    facture_url = Column(String, nullable=True, comment="Lien Cloudinary PDF")
    date_creation = Column(DateTime, default=datetime.utcnow)

    organisation = relationship("Organisation", back_populates="abonnements")

    @property
    def est_en_retard(self) -> bool:
        if self.statut_paiement == StatutPaiement.PAYE:
            return False
        if self.date_echeance and self.date_echeance < datetime.utcnow().date():
            return True
        return False