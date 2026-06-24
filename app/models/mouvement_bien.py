# backend/app/models/mouvement_bien.py
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum

class TypeMouvementEnum(enum.Enum):
    TRANSFERT = "TRANSFERT"
    SORTIE = "SORTIE"
    CESSION = "CESSION"
    AFFECTATION = "AFFECTATION"
    RETOUR = "RETOUR"

class MouvementBien(Base):
    __tablename__ = "mouvements_biens"
    
    id_mouvement = Column(Integer, primary_key=True, index=True)
    
    # ✅ Clés étrangères - CORRECTION : pointer vers 'utilisateurs.id' (PK réelle)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)  # ← 'id' et non 'id_utilisateur'
    
    # Données du mouvement
    type_mouvement = Column(SQLEnum(TypeMouvementEnum), nullable=False)
    date_mouvement = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Localisation et responsabilités
    localisation_source = Column(String(200), nullable=True)
    localisation_destination = Column(String(200), nullable=True)
    responsable_sortie = Column(String(200), nullable=True)
    
    # Justification et pièces
    raison = Column(Text, nullable=False)
    piece_justificative = Column(String(500), nullable=True)
    
    # Métadonnées
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # ✅ Relations bidirectionnelles
    bien = relationship("Bien", back_populates="mouvements", foreign_keys=[id_bien])
    
    # ✅ CORRECTION : back_populates doit matcher exactement le nom dans Utilisateur
    utilisateur = relationship(
        "Utilisateur",
        back_populates="mouvements_realises",  # ← Doit exister dans Utilisateur
        foreign_keys=[id_utilisateur],
        lazy="select"
    )