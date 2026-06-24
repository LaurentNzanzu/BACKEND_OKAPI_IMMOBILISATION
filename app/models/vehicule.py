from sqlalchemy import Column, String, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from .bien import Bien

class Vehicule(Bien):
    __tablename__ = "vehicules"
    
    id_bien = Column(Integer, ForeignKey('biens.id_bien'), primary_key=True)
    type_vehicule = Column(String(100))  # Voiture, Moto, Camion, etc.
    marque = Column(String(100))
    modele = Column(String(100))
    immatriculation = Column(String(50), unique=True)
    poids = Column(Float)  # en kg
    dimension = Column(String(100))  # L x l x h
    type_carburant = Column(String(50))  # Essence, Diesel, Electrique, etc.
    consommation_carburant = Column(Float)  # L/100km
    consommation_huile = Column(Float)  # L/1000km
    type_propulsion = Column(String(50))  # 4x2, 4x4, etc.
    
    __mapper_args__ = {
        "polymorphic_identity": "vehicule",
    }