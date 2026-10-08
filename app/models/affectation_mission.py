from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from ..core.database import Base

class AffectationMission(Base):
    __tablename__ = "affectations_mission"
    id = Column(Integer, primary_key=True)
    organisation_id = Column(Integer, ForeignKey("organisations.id"), nullable=False, index=True)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=False, index=True)
    vehicule_id = Column(Integer, ForeignKey("vehicules.id_bien"), nullable=True, index=True)
    chauffeur_id = Column(Integer, ForeignKey("chauffeurs.id"), nullable=True, index=True)
    date_debut = Column(DateTime, nullable=False)
    date_fin = Column(DateTime, nullable=False)
    statut = Column(String(50), default="PLANIFIEE")
    commentaire = Column(Text)
    affecte_par = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True, index=True)
    date_affectation = Column(DateTime, default=datetime.utcnow)

    mission = relationship("Mission", back_populates="affectations")
    vehicule = relationship("Vehicule")
    chauffeur = relationship("Chauffeur")
    utilisateur_affecteur = relationship("Utilisateur", foreign_keys=[affecte_par])