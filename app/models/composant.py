# backend/app/models/composant.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class Composant(Base):
    __tablename__ = "composants"

    id_composant = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    designation = Column(String(200), nullable=False)
    numero_serie = Column(String(100), nullable=True)
    prix_achat = Column(Numeric(10, 2), nullable=True)
    valeur = Column(Float, nullable=False)
    duree_vie_ans = Column(Integer, nullable=False)
    date_remplacement = Column(DateTime, nullable=True)
    date_mise_en_service = Column(DateTime, nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)

    bien = relationship("Bien", back_populates="composants")
