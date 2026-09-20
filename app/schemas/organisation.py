# app/schemas/organisation.py
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator
from datetime import datetime, date
from typing import Optional
from enum import Enum


class PlanAbonnementEnum(str, Enum):
    BASIC = "BASIC"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class StatutOrganisationEnum(str, Enum):
    ACTIF = "ACTIF"
    SUSPENDU = "SUSPENDU"
    EXPIRE = "EXPIRE"


class OrganisationCreate(BaseModel):
    nom: str = Field(..., min_length=2, max_length=200)
    code: str = Field(..., min_length=2, max_length=50)
    email_admin: EmailStr = Field(...)
    plan_abonnement: PlanAbonnementEnum = PlanAbonnementEnum.BASIC
    quota_vehicules: int = Field(default=10, ge=0)
    quota_chauffeurs: int = Field(default=10, ge=0)
    quota_missions_mois: int = Field(default=50, ge=0)
    devise: str = Field(default="USD", min_length=3, max_length=3)
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None

    @field_validator("code")
    @classmethod
    def code_upper(cls, v: str) -> str:
        return v.strip().upper()


class OrganisationUpdate(BaseModel):
    nom: Optional[str] = Field(None, min_length=2, max_length=200)
    email_admin: Optional[EmailStr] = None
    plan_abonnement: Optional[PlanAbonnementEnum] = None
    quota_vehicules: Optional[int] = Field(None, ge=0)
    quota_chauffeurs: Optional[int] = Field(None, ge=0)
    quota_missions_mois: Optional[int] = Field(None, ge=0)
    devise: Optional[str] = Field(None, min_length=3, max_length=3)
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    statut: Optional[StatutOrganisationEnum] = None


class OrganisationResponse(BaseModel):
    id: int
    nom: str
    code: str
    email_admin: str
    plan_abonnement: PlanAbonnementEnum
    quota_vehicules: int
    quota_chauffeurs: int
    quota_missions_mois: int
    devise: str
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    statut: StatutOrganisationEnum
    date_creation: Optional[datetime] = None
    date_modification: Optional[datetime] = None

    # Champs calculés
    plan_info: Optional[dict] = None
    quota_utilise: Optional[dict] = Field(
        default_factory=dict,
        description="Compteurs d'utilisation : véhicules, chauffeurs, missions du mois",
    )

    model_config = ConfigDict(from_attributes=True)