from sqlalchemy import Column, String, Integer, Float, ForeignKey, Numeric
from .bien import Bien


class Machine(Bien):
    __tablename__ = "machines"

    id_bien = Column(Integer, ForeignKey('biens.id_bien'), primary_key=True)
    fabricant = Column(String(100))
    modele = Column(String(100))
    puissance = Column(Float)
    type_alimentation = Column(String(50))
    tension_normal = Column(String(50))
    service_affecte = Column(String(200))
    responsable = Column(String(100))
    consommation_elec = Column(Float)
    frequence_maintenance = Column(String(50))
    prix_base = Column(Numeric(10, 2), nullable=True)
    unites_totales_prevues = Column(Integer, nullable=True)
    unites_consommees = Column(Integer, nullable=True)
    duree_fournisseur = Column(Integer, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "machine",
    }
