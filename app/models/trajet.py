from ..core.database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship

class Trajet(Base):
    __tablename__ = "trajets"
    id = Column(Integer, primary_key=True)
    organisation_id = Column(Integer, ForeignKey("organisations.id"), nullable=False, index=True)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=True, index=True)
    mouvement_bien_id = Column(Integer, ForeignKey("mouvements_biens.id_mouvement"), nullable=True)
    vehicule_id = Column(Integer, ForeignKey("vehicules.id_bien"), nullable=True)
    chauffeur_id = Column(Integer, ForeignKey("chauffeurs.id"), nullable=True)
    date_debut = Column(DateTime)
    date_fin = Column(DateTime)
    kilometrage_debut = Column(Float)
    kilometrage_fin = Column(Float)
    distance_km = Column(Float)
    statut = Column(String(50), default="EN_COURS")
    commentaire = Column(Text)
    mission = relationship("Mission", back_populates="trajets")
    mouvement_bien = relationship("MouvementBien", foreign_keys=[mouvement_bien_id])
    vehicule = relationship("Vehicule")
    chauffeur = relationship("Chauffeur")