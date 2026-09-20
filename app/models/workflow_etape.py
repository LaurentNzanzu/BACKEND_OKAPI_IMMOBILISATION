# app/models/workflow_etape.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class TypeWorkflow(str, enum.Enum):
    MISSION = "MISSION"
    RAVITAILLEMENT = "RAVITAILLEMENT"
    INCIDENT = "INCIDENT"


class WorkflowEtape(Base):
    __tablename__ = "workflow_etapes"

    id = Column(Integer, primary_key=True, index=True)
    organisation_id = Column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type_workflow = Column(SQLEnum(TypeWorkflow), nullable=False, index=True)
    ordre = Column(Integer, nullable=False, comment="Étape 1, 2, 3…")
    role_requis = Column(String(50), nullable=True, comment="Rôle qui valide cette étape")
    permission_requise = Column(String(50), nullable=True, comment="Permission granulaire")
    condition = Column(JSON, nullable=True, comment='Ex: {"seuil_montant": 1000}')
    est_optionnelle = Column(Boolean, default=False, nullable=False)
    actif = Column(Boolean, default=True, nullable=False)
    date_creation = Column(DateTime, default=datetime.utcnow)

    organisation = relationship("Organisation", back_populates="workflow_etapes")

    @property
    def condition_remplie(self) -> bool:
        """Vérifie si la condition JSON est définie (évaluation déléguée au service)."""
        return self.condition is not None and len(self.condition) > 0