
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, ForeignKey, Text, DateTime
from ..core.database import Base


class Mission(Base):
    __tablename__ = "missions"
    id = Column(Integer, primary_key=True, index=True)
    organisation_id = Column(Integer, ForeignKey("organisations.id"), nullable=False, index=True)
    projet_id = Column(Integer, ForeignKey("projets.id"), nullable=True, index=True)
    type_workflow = Column(String(50), nullable=False, default="MISSION")
    statut = Column(String(50), nullable=False, default="BROUILLON")
    description = Column(Text)
    lieu_depart = Column(String(255))
    lieu_arrivee = Column(String(255))
    date_debut = Column(DateTime)
    date_fin = Column(DateTime)
    date_creation = Column(DateTime, default=datetime.utcnow)
    cree_par = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    projet = relationship("Projet", back_populates="missions")
    affectations = relationship("AffectationMission", back_populates="mission", cascade="all, delete-orphan")
    trajets = relationship("Trajet", back_populates="mission", cascade="all, delete-orphan")