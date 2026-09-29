from datetime import datetime
from sqlalchemy import Column, String, Integer, Date, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from ..core.database import Base


class Chauffeur(Base):
    __tablename__ = "chauffeurs"
    id = Column(Integer, primary_key=True, index=True)
    organisation_id = Column(Integer, ForeignKey("organisations.id"), nullable=False, index=True)
    nom = Column(String(100), nullable=False)
    prenom = Column(String(100), nullable=False)
    telephone = Column(String(50))
    numero_permis = Column(String(100), nullable=False)
    type_permis = Column(String(50))
    date_expiration_permis = Column(Date)
    disponible = Column(Boolean, default=True)
    actif = Column(Boolean, default=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    organisation = relationship("Organisation")