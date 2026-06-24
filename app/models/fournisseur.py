# backend/app/models/fournisseur.py
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base

class Fournisseur(Base):
    __tablename__ = "fournisseurs"
    
    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(200), nullable=False, index=True)
    adresse = Column(String(500), nullable=True)
    telephone = Column(String(50), nullable=True)
    email = Column(String(100), nullable=True)
    numero_contribuable = Column(String(50), nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    
    # Relation
    biens = relationship("Bien", back_populates="fournisseur", foreign_keys="Bien.fournisseur_id")