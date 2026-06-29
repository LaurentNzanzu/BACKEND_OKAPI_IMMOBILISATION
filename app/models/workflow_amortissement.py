# backend/app/models/workflow_amortissement.py
import enum
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class EtapeWorkflowAmortissement(enum.Enum):
    COMPTABLE = "COMPTABLE"
    CAISSE = "CAISSE"
    DG = "DG"
    COMPTABLE_VALIDATION = "COMPTABLE_VALIDATION"


class StatutWorkflowAmortissement(enum.Enum):
    EN_ATTENTE = "EN_ATTENTE"
    APPROUVE = "APPROUVE"
    REJETE = "REJETE"
    SUSPENDU = "SUSPENDU"


class WorkflowValidationAmortissement(Base):
    __tablename__ = "workflow_validation_amortissement"

    id_workflow = Column(Integer, primary_key=True, index=True)
    id_amortissement = Column(Integer, ForeignKey("amortissements.id_amortissement", ondelete="CASCADE"), nullable=False)
    
    etape = Column(SQLEnum(EtapeWorkflowAmortissement), nullable=False)
    statut = Column(SQLEnum(StatutWorkflowAmortissement), default=StatutWorkflowAmortissement.EN_ATTENTE, nullable=False)
    
    id_validateur = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    date_validation = Column(DateTime, nullable=True)
    commentaire = Column(Text, nullable=True)
    
    piece_justificative_url = Column(String(500), nullable=True)
    bon_decaissement_pdf = Column(String(500), nullable=True)

    # Relationships
    amortissement = relationship("Amortissement", backref="validations_workflow")
    validateur = relationship("Utilisateur", foreign_keys=[id_validateur])
