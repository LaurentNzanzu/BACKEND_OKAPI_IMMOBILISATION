# app/models/projet.py
from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class Projet(Base):
    __tablename__ = "projets"

    id = Column(Integer, primary_key=True, index=True)
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code = Column(String(50), nullable=False, comment="Code unique par organisation")
    nom = Column(String(200), nullable=False)
    bailleur = Column(String(200), nullable=True)
    budget_annuel = Column(Numeric(14, 2), default=0.0)
    devise = Column(String(3), default="USD", nullable=False)
    date_debut = Column(Date, nullable=True)
    date_fin = Column(Date, nullable=True)
    est_actif = Column(Boolean, default=True, nullable=False)
    date_creation = Column(DateTime, default=datetime.utcnow)

    organisation = relationship("Organisation", back_populates="projets")
    #missions = relationship("Mission", back_populates="projet")
    #approvisionnements = relationship("ApprovisionnementCarburant", back_populates="projet")

    __table_args__ = (
        # Un code projet unique par organisation
        # (à décommenter si vous utilisez UniqueConstraint)
        # UniqueConstraint("organisation_id", "code", name="uq_projet_code_org"),
    )

    @property
    def est_en_cours(self) -> bool:
        today = datetime.utcnow().date()
        if self.date_debut and today < self.date_debut:
            return False
        if self.date_fin and today > self.date_fin:
            return False
        return self.est_actif