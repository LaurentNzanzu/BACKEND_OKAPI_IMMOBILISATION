# backend/app/models/decision_ia.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum

class TypeDecisionEnum(enum.Enum):
    HEALTH_SCORE = "HEALTH_SCORE"
    PREDICTION_PANNE = "PREDICTION_PANNE"
    ACHAT_RECOMMANDE = "ACHAT_RECOMMENDE"  # valeur typedecisionenum PostgreSQL
    DECISION_STRATEGIQUE = "DECISION_STRATEGIQUE"
    SCAN_PIECE = "SCAN_PIECE"

class DecisionIA(Base):
    __tablename__ = 'decisions_ia'

    id_decision = Column(Integer, primary_key=True, index=True)  # ✅ Renommé pour cohérence
    id_bien = Column(Integer, ForeignKey('biens.id_bien'), nullable=True)
    id_utilisateur = Column(Integer, ForeignKey('utilisateurs.id'), nullable=True)
    id_piece = Column(Integer, ForeignKey('pieces_rechange.id_piece'), nullable=True)
    
    type_decision = Column(
        SQLEnum(
            TypeDecisionEnum,
            name="typedecisionenum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    score = Column(Float, nullable=True)
    statut = Column(String(50), nullable=True)
    contenu = Column(Text, nullable=False)  # ✅ Ne doit pas être NULL
    source_modele = Column(String(100), nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)

    # Relations (à compléter dans Bien et Utilisateur)
    bien = relationship("Bien", back_populates="decisions_ia", foreign_keys=[id_bien])
    piece = relationship("PieceRechange", foreign_keys=[id_piece]) # Relation optionnelle vers PieceRechange
    utilisateur = relationship("Utilisateur", back_populates="decisions_ia", foreign_keys=[id_utilisateur])