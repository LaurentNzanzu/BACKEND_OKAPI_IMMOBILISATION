from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum

class OrdreValidation(enum.Enum):
    DG = "DG"
    COMPTABLE = "COMPTABLE"
    CAISSE = "CAISSE"

class DecisionValidation(enum.Enum):
    APPROUVE = "APPROUVE"
    REJETE = "REJETE"
    EN_ATTENTE = "EN_ATTENTE"

class Validation(Base):
    __tablename__ = "validations"

    id_validation = Column(Integer, primary_key=True, index=True)
    id_besoin = Column(Integer, ForeignKey("besoins.id_besoin", ondelete="CASCADE"), nullable=False)
    id_validateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)
    ordre_validateur = Column(SQLEnum(OrdreValidation), nullable=False)
    decision = Column(SQLEnum(DecisionValidation), default=DecisionValidation.EN_ATTENTE)
    date_validation = Column(DateTime, default=datetime.utcnow)
    commentaire = Column(Text, nullable=True)

    # Relations
    besoin = relationship("Besoin", back_populates="validations")
    validateur = relationship("Utilisateur", foreign_keys=[id_validateur])