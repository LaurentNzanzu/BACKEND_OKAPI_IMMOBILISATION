import enum
from ..core.database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship


class SourceDonneesTrajet(str, enum.Enum):
    MOBILE = "MOBILE"
    BOITIER = "BOITIER"


class StatutTrajet(str, enum.Enum):
    EN_COURS = "EN_COURS"
    TERMINE = "TERMINE"
    ANOMALIE = "ANOMALIE"


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
    lat_depart = Column(Float, nullable=True)
    lng_depart = Column(Float, nullable=True)
    lat_arrivee = Column(Float, nullable=True)
    lng_arrivee = Column(Float, nullable=True)
    carburant_consomme_estime = Column(Float, nullable=True)
    source_donnees = Column(String(50), default=SourceDonneesTrajet.MOBILE.value, nullable=False)
    statut = Column(String(50), default=StatutTrajet.EN_COURS.value, nullable=False)
    commentaire = Column(Text)

    mission = relationship("Mission", back_populates="trajets")
    mouvement_bien = relationship("MouvementBien", foreign_keys=[mouvement_bien_id])
    vehicule = relationship("Vehicule")
    chauffeur = relationship("Chauffeur")

    # Alias de compatibilité
    @property
    def id_mission(self):
        return self.mission_id

    @property
    def id_bien(self):
        return self.vehicule_id

    @property
    def id_chauffeur(self):
        return self.chauffeur_id

    @property
    def heure_depart(self):
        return self.date_debut

    @heure_depart.setter
    def heure_depart(self, value):
        self.date_debut = value

    @property
    def heure_arrivee(self):
        return self.date_fin

    @heure_arrivee.setter
    def heure_arrivee(self, value):
        self.date_fin = value

    @property
    def km_depart(self):
        return self.kilometrage_debut

    @km_depart.setter
    def km_depart(self, value):
        self.kilometrage_debut = value

    @property
    def km_arrivee(self):
        return self.kilometrage_fin

    @km_arrivee.setter
    def km_arrivee(self, value):
        self.kilometrage_fin = value

    @property
    def km_parcourus(self):
        return self.distance_km

    @km_parcourus.setter
    def km_parcourus(self, value):
        self.distance_km = value