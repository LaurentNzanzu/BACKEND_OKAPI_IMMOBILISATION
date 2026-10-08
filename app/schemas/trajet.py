from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrajetBase(BaseModel):
    mission_id: Optional[int] = None
    mouvement_bien_id: Optional[int] = None
    vehicule_id: Optional[int] = None
    chauffeur_id: Optional[int] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None
    kilometrage_debut: Optional[float] = None
    kilometrage_fin: Optional[float] = None
    distance_km: Optional[float] = None
    lat_depart: Optional[float] = None
    lng_depart: Optional[float] = None
    lat_arrivee: Optional[float] = None
    lng_arrivee: Optional[float] = None
    carburant_consomme_estime: Optional[float] = None
    source_donnees: Optional[str] = "MOBILE"
    statut: Optional[str] = "EN_COURS"
    commentaire: Optional[str] = None


class TrajetCreate(TrajetBase):
    @model_validator(mode="after")
    def validate_trajet_create(self) -> "TrajetCreate":
        if self.kilometrage_debut is not None and self.kilometrage_fin is not None:
            if self.kilometrage_fin < self.kilometrage_debut:
                raise ValueError("Le kilométrage de fin ne peut pas être inférieur au kilométrage de début")
        if self.date_debut is not None and self.date_fin is not None:
            if self.date_fin < self.date_debut:
                raise ValueError("La date de fin ne peut pas être antérieure à la date de début")
        return self


class TrajetUpdate(BaseModel):
    mission_id: Optional[int] = None
    mouvement_bien_id: Optional[int] = None
    vehicule_id: Optional[int] = None
    chauffeur_id: Optional[int] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None
    kilometrage_debut: Optional[float] = None
    kilometrage_fin: Optional[float] = None
    distance_km: Optional[float] = None
    lat_depart: Optional[float] = None
    lng_depart: Optional[float] = None
    lat_arrivee: Optional[float] = None
    lng_arrivee: Optional[float] = None
    carburant_consomme_estime: Optional[float] = None
    source_donnees: Optional[str] = None
    statut: Optional[str] = None
    commentaire: Optional[str] = None

    @model_validator(mode="after")
    def validate_trajet_update(self) -> "TrajetUpdate":
        if self.kilometrage_debut is not None and self.kilometrage_fin is not None:
            if self.kilometrage_fin < self.kilometrage_debut:
                raise ValueError("Le kilométrage de fin ne peut pas être inférieur au kilométrage de début")
        if self.date_debut is not None and self.date_fin is not None:
            if self.date_fin < self.date_debut:
                raise ValueError("La date de fin ne peut pas être antérieure à la date de début")
        return self


class TrajetResponse(TrajetBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organisation_id: int


# Alias rétrocompatible
TrajetRead = TrajetResponse

