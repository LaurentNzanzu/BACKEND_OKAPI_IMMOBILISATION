# backend/app/models/centre_cout.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from ..core.database import Base


class CentreCout(Base):
    __tablename__ = "centres_cout"

    id = Column(Integer, primary_key=True, index=True)

    # ═══ 5.22 — Multi-tenant ═══
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Multi-tenant : ONG propriétaire"
    )
    # ═══ FIN 5.22 ═══

    code = Column(String(50), nullable=False, index=True)   # ═══ 5.22 — unique retiré ═══
    nom = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    actif = Column(Boolean, default=True, nullable=False)

    # Relations
    organisation = relationship("Organisation")   # ═══ 5.22 ═══

    # ═══ 5.22 — Contrainte UNIQUE scopée par ONG ═══
    __table_args__ = (
        UniqueConstraint('organisation_id', 'code', name='uq_centre_cout_org_code'),
    )
    # ═══ FIN 5.22 ═══