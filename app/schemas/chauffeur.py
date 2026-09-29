from typing import Optional
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict

class ChauffeurBase(BaseModel):
    nom: str
    prenom: str
    telephone: Optional[str] = None
    numero_permis: str
    type_permis: Optional[str] = None
    date_expiration_permis: Optional[date] = None
    disponible: Optional[bool] = True
    actif: Optional[bool] = True

class ChauffeurCreate(ChauffeurBase): pass
class ChauffeurUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    numero_permis: Optional[str] = None
    type_permis: Optional[str] = None
    date_expiration_permis: Optional[date] = None
    disponible: Optional[bool] = None
    actif: Optional[bool] = None

class ChauffeurRead(ChauffeurBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organisation_id: int
    date_creation: datetime
