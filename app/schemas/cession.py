from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional
from datetime import date, datetime
from decimal import Decimal


class CessionCreate(BaseModel):
    id_bien: int
    date_cession: date
    prix_vente: Optional[float] = Field(None, gt=0)
    prix_cession: Optional[float] = Field(None, gt=0)
    valeur_nette_comptable: Optional[float] = Field(None, ge=0)
    acheteur: Optional[str] = None
    mode_reglement: Optional[str] = None
    type_cession: Literal["courante", "non_courante"] = "courante"
    motif: Optional[str] = None

    @model_validator(mode="after")
    def resolve_prix(self):
        if self.prix_vente is None and self.prix_cession is not None:
            self.prix_vente = self.prix_cession
        if self.prix_vente is None:
            raise ValueError("prix_vente ou prix_cession est requis")
        return self


class RebutCreate(BaseModel):
    id_bien: int
    date_rebut: Optional[date] = None
    motif: str = Field(..., min_length=3)


class CessionResponse(BaseModel):
    id_cession: int
    id_bien: int
    date_cession: date
    prix_vente: Decimal
    acheteur: Optional[str] = None
    mode_reglement: Optional[str] = None
    type_cession: str
    resultat: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True