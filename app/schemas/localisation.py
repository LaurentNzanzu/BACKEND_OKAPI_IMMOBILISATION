from pydantic import BaseModel, Field, field_validator
from typing import List


class LocalisationBase(BaseModel):
    nom_localisation: str = Field(..., min_length=1, max_length=200)


class LocalisationCreate(LocalisationBase):
    @field_validator("nom_localisation", mode="before")
    @classmethod
    def normalize_name(cls, value):
        if isinstance(value, str):
            return " ".join(value.split()).upper()
        return value


class LocalisationResponse(LocalisationBase):
    id_localisation: int

    class Config:
        from_attributes = True


class LocalisationListResponse(BaseModel):
    total: int
    localisations: List[LocalisationResponse]
