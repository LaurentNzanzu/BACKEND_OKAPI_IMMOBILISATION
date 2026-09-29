from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class MissionBase(BaseModel):
    projet_id: Optional[int] = None
    type_workflow: Optional[str] = "MISSION"
    statut: Optional[str] = "BROUILLON"
    description: Optional[str] = None
    lieu_depart: Optional[str] = None
    lieu_arrivee: Optional[str] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None


class MissionCreate(MissionBase):
    pass


class MissionUpdate(BaseModel):
    projet_id: Optional[int] = None
    type_workflow: Optional[str] = None
    statut: Optional[str] = None
    description: Optional[str] = None
    lieu_depart: Optional[str] = None
    lieu_arrivee: Optional[str] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None


class MissionRead(MissionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organisation_id: int
    date_creation: datetime
    cree_par: Optional[int] = None

