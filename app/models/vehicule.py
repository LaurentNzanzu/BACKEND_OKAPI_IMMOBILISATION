import enum
from sqlalchemy import Column, String, Integer, Float, ForeignKey, Date
from sqlalchemy.orm import relationship
from .bien import Bien


class CategorieVehicule(str, enum.Enum):
    CAMION = "CAMION"
    VOITURE = "VOITURE"
    MOTO = "MOTO"
    BUS = "BUS"


class Vehicule(Bien):
    """
    Extension opérationnelle d'un Bien patrimonial pour la gestion de flotte.
    
    Choix d'architecture pour le compteur kilométrique :
    `kilometrage_actuel` est stocké en colonne `Float` (défaut 0.0) directement sur la
    table `vehicules` pour garantir le typage fort, la cohérence transactionnelle,
    l'interdiction des régressions de compteur et la performance d'indexation
    sans nécessiter de sérialisation JSON dans `attributs_specifiques`.
    """
    __tablename__ = "vehicules"
    
    id_bien = Column(Integer, ForeignKey('biens.id_bien', ondelete="CASCADE"), primary_key=True)
    categorie = Column(String(50), default=CategorieVehicule.VOITURE.value, nullable=True)
    marque = Column(String(100), nullable=True)
    modele = Column(String(100), nullable=True)
    # Scoped uniqueness is enforced transactionally with the parent Bien's organisation.
    immatriculation = Column(String(50), nullable=True)
    poids = Column(Float, nullable=True)  # en kg
    dimension = Column(String(100), nullable=True)  # L x l x h
    type_carburant = Column(String(50), nullable=True)  # Essence, Diesel, Electrique, etc.
    consommation_carburant = Column(Float, nullable=True)  # L/100km
    consommation_theorique = Column(Float, nullable=True)  # L/100km théorique
    consommation_huile = Column(Float, nullable=True)  # L/1000km
    type_propulsion = Column(String(50), nullable=True)  # 4x2, 4x4, etc.
    
    # Caractéristiques et suivi de flotte
    vin = Column(String(100), nullable=True)
    numero_boitier_gps = Column(String(100), nullable=True)
    date_expiration_assurance = Column(Date, nullable=True)
    date_expiration_visite_technique = Column(Date, nullable=True)
    date_expiration_permis_transport = Column(Date, nullable=True)
    capacite_reservoir = Column(Float, nullable=True)
    kilometrage_actuel = Column(Float, default=0.0, nullable=False)
    prochain_km_maintenance = Column(Float, nullable=True)
    couleur = Column(String(50), nullable=True)
    nombre_places = Column(Integer, nullable=True)
    
    __mapper_args__ = {
        "polymorphic_identity": "vehicule",
    }

    # Rétrocompatibilité type_vehicule <-> categorie
    @property
    def type_vehicule(self) -> str | None:
        return self.categorie

    @type_vehicule.setter
    def type_vehicule(self, value: str | None):
        self.categorie = value