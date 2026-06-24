from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from .bien import Bien

class Ordinateur(Bien):
    __tablename__ = "ordinateurs"
    
    id_bien = Column(Integer, ForeignKey('biens.id_bien'), primary_key=True)
    marque = Column(String(100))
    modele = Column(String(100))
    processeur = Column(String(100))  # Intel i5, i7, etc.
    ram = Column(String(50))  # 8GB, 16GB, etc.
    stockage = Column(String(100))  # 256GB SSD, 1TB HDD, etc.
    adresse_ip = Column(String(50))
    utilisateur_affecte = Column(String(100))
    
    __mapper_args__ = {
        "polymorphic_identity": "ordinateur",
    }