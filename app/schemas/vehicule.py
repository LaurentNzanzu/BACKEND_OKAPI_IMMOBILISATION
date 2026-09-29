from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class VehiculeBase(BaseModel):
    type_vehicule: Optional[str] = None
    marque: Optional[str] = None
    modele: Optional[str] = None
    poids: Optional[float] = None
    dimension: Optional[str] = None
    type_carburant: Optional[str] = None
    consommation_carburant: Optional[float] = None
    consommation_huile: Optional[float] = None
    type_propulsion: Optional[str] = None

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
    immatriculation: Optional[str] = Field(None, min_length=1, max_length=50)
    id_localisation: Optional[int] = Field(None, gt=0)
    description: Optional[str] = None
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = Field(None, ge=0)
    date_fin_garantie: Optional[date] = None

class VehiculeRead(VehiculeBase):
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

