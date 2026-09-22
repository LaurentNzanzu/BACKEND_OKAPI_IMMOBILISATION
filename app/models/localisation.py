# backend/app/models/localisation.py
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from ..core.database import Base


class Localisation(Base):
    __tablename__ = "localisations"

    id_localisation = Column(Integer, primary_key=True, index=True)

    # ═══ 5.22 — Multi-tenant ═══
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Multi-tenant : ONG propriétaire"
    )
    # ═══ FIN 5.22 ═══

    nom_localisation = Column(String(200), nullable=False, index=True)   # ═══ 5.22 — unique retiré ═══

    # Relations
    organisation = relationship("Organisation")   # ═══ 5.22 ═══
    biens = relationship("Bien", back_populates="localisation_ref")

    # ═══ 5.22 — Contrainte UNIQUE scopée par ONG ═══
    __table_args__ = (
        UniqueConstraint('organisation_id', 'nom_localisation', name='uq_localisation_org_nom'),
    )
    # ═══ FIN 5.22 ═══