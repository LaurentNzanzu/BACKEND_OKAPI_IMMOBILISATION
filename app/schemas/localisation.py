from pydantic import BaseModel, Field
from typing import List


class LocalisationBase(BaseModel):
    nom_localisation: str = Field(..., min_length=1, max_length=200)


class LocalisationCreate(LocalisationBase):
    pass


class LocalisationResponse(LocalisationBase):
    id_localisation: int

    class Config:
        from_attributes = True


class LocalisationListResponse(BaseModel):
    total: int
    localisations: List[LocalisationResponse]
