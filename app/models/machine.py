from sqlalchemy import Column, String, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from .bien import Bien

class Machine(Bien):
    __tablename__ = "machines"
    
    id_bien = Column(Integer, ForeignKey('biens.id_bien'), primary_key=True)
    numero_serie = Column(String(100), unique=True)
    fabricant = Column(String(100))
    modele = Column(String(100))
    puissance = Column(Float)  # en kW ou CV
    type_alimentation = Column(String(50))  # Electrique, Hydraulique, Pneumatique
    tension_normal = Column(String(50))  # 220V, 380V, etc.
    service_affecte = Column(String(200))
    responsable = Column(String(100))
    consommation_elec = Column(Float)  # kWh
    frequence_maintenance = Column(String(50))  # Quotidienne, Hebdomadaire, etc.
    
    __mapper_args__ = {
        "polymorphic_identity": "machine",
    }