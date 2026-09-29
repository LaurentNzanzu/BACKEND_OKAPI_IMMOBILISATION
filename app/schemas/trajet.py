from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


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
    statut: Optional[str] = "EN_COURS"
    commentaire: Optional[str] = None


class TrajetCreate(TrajetBase):
    pass


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
    statut: Optional[str] = None
    commentaire: Optional[str] = None


class TrajetRead(TrajetBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organisation_id: int
