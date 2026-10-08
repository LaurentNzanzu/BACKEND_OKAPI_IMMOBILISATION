from datetime import date
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

VALID_CATEGORIES_VEHICULE = {"CAMION", "VOITURE", "MOTO", "BUS"}


class VehiculeBase(BaseModel):
    categorie: Optional[str] = "VOITURE"
    type_vehicule: Optional[str] = None
    marque: Optional[str] = None
    modele: Optional[str] = None
    poids: Optional[float] = None
    dimension: Optional[str] = None
    type_carburant: Optional[str] = None
    consommation_carburant: Optional[float] = None
    consommation_theorique: Optional[float] = None
    consommation_huile: Optional[float] = None
    type_propulsion: Optional[str] = None
    vin: Optional[str] = None
    numero_boitier_gps: Optional[str] = None
    date_expiration_assurance: Optional[date] = None
    date_expiration_visite_technique: Optional[date] = None
    date_expiration_permis_transport: Optional[date] = None
    capacite_reservoir: Optional[float] = None
    kilometrage_actuel: Optional[float] = 0.0
    prochain_km_maintenance: Optional[float] = None
    couleur: Optional[str] = None
    nombre_places: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def sync_categorie(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "type_vehicule" in data and "categorie" not in data:
                data["categorie"] = str(data["type_vehicule"]).upper()
            elif "categorie" in data and "type_vehicule" not in data:
                data["type_vehicule"] = data["categorie"]
        return data

    @model_validator(mode="after")
    def validate_categorie_enum(self) -> "VehiculeBase":
        if self.categorie:
            cat = self.categorie.upper()
            if cat not in VALID_CATEGORIES_VEHICULE:
                raise ValueError(f"Catégorie de véhicule invalide : {self.categorie}. Autorisées : {', '.join(VALID_CATEGORIES_VEHICULE)}")
            self.categorie = cat
        return self


class VehiculeCreate(VehiculeBase):
    immatriculation: str = Field(..., min_length=1, max_length=50)
    libelle: str = Field(..., min_length=1, max_length=200)
    id_localisation: int = Field(..., gt=0)
    numero_inventaire: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = Field(None, ge=0)
    date_fin_garantie: Optional[date] = None


class VehiculeUpdate(VehiculeBase):
    categorie: Optional[str] = None
    immatriculation: Optional[str] = Field(None, min_length=1, max_length=50)
    id_localisation: Optional[int] = Field(None, gt=0)
    description: Optional[str] = None
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = Field(None, ge=0)
    date_fin_garantie: Optional[date] = None


class VehiculeResponse(VehiculeBase):
    id_bien: int
    organisation_id: int
    immatriculation: str
    libelle: str
    id_localisation: int
    numero_inventaire: str
    description: Optional[str] = None
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = None
    date_fin_garantie: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


# Alias rétrocompatible
VehiculeRead = VehiculeResponse


