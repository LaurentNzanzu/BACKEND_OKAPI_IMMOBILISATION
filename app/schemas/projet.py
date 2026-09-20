# app/schemas/projet.py
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime, date
from decimal import Decimal
from typing import Optional


class ProjetCreate(BaseModel):
    organisation_id: int = Field(..., gt=0)
    code: str = Field(..., min_length=2, max_length=50)
    nom: str = Field(..., min_length=2, max_length=200)
    bailleur: Optional[str] = Field(None, max_length=200)
    budget_annuel: Decimal = Field(default=Decimal("0.00"), ge=0)
    devise: str = Field(default="USD", min_length=3, max_length=3)
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    est_actif: bool = True

    @field_validator("code")
    @classmethod
    def code_upper(cls, v: str) -> str:
        return v.strip().upper()


class ProjetUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    nom: Optional[str] = Field(None, min_length=2, max_length=200)
    bailleur: Optional[str] = None
    budget_annuel: Optional[Decimal] = Field(None, ge=0)
    devise: Optional[str] = Field(None, min_length=3, max_length=3)
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    est_actif: Optional[bool] = None


class ProjetResponse(BaseModel):
    id: int
    organisation_id: int
    code: str
    nom: str
    bailleur: Optional[str] = None
    budget_annuel: Decimal
    devise: str
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    est_actif: bool
    date_creation: Optional[datetime] = None

    # Champs calculés
    budget_consomme: Optional[Decimal] = Field(default=Decimal("0.00"))
    budget_restant: Optional[Decimal] = Field(default=Decimal("0.00"))
    est_en_cours: bool = True

    model_config = ConfigDict(from_attributes=True)