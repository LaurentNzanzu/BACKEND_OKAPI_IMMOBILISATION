# backend/app/models/type_bien.py
from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class TypeBien(Base):
    """
    Modèle représentant un type de bien dynamique.
    Permet aux utilisateurs de créer de nouvelles catégories de biens.
    """
    __tablename__ = "types_biens"

    id = Column(Integer, primary_key=True, index=True)
    libelle = Column(String(100), unique=True, nullable=False, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    
    # Compte comptable SYSCOHADA par défaut pour ce type (ex: 2440, 2445, etc.)
    compte_comptable = Column(String(10), nullable=False, default="2440")
    
    # Définition des champs spécifiques au type (JSON)
    # Exemple: {"champs": ["marque", "modele", "numero_serie", "puissance"]}
    # Ou plus avancé: {"champs": [{"nom": "marque", "type": "text", "obligatoire": true}]}
    champs_specifiques = Column(JSON, default=list)
    
    # Description du type de bien
    description = Column(Text, nullable=True)
    
    # Indique si le type est actif
    est_actif = Column(Boolean, default=True)
    
    # Timestamps
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_modification = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    biens = relationship("Bien", back_populates="type_bien_ref")

    def __repr__(self):
        return f"<TypeBien(id={self.id}, libelle='{self.libelle}', code='{self.code}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "libelle": self.libelle,
            "code": self.code,
            "compte_comptable": self.compte_comptable,
            "champs_specifiques": self.champs_specifiques,
            "description": self.description,
            "est_actif": self.est_actif,
            "date_creation": self.date_creation.isoformat() if self.date_creation else None,
            "date_modification": self.date_modification.isoformat() if self.date_modification else None
        }