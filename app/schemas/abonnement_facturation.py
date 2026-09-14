# app/schemas/abonnement_facturation.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from enum import Enum


class StatutPaiementEnum(str, Enum):
    EN_ATTENTE = "EN_ATTENTE"
    PAYE = "PAYE"
    RETARD = "RETARD"


class AbonnementFacturationCreate(BaseModel):
    organisation_id: int = Field(..., gt=0)
    periode: str = Field(..., min_length=4, max_length=20)
    montant: Decimal = Field(..., gt=0)
    devise: str = Field(default="USD", min_length=3, max_length=3)
    statut_paiement: StatutPaiementEnum = StatutPaiementEnum.EN_ATTENTE
    date_echeance: Optional[date] = None
    facture_url: Optional[str] = None


class AbonnementFacturationUpdate(BaseModel):
    statut_paiement: Optional[StatutPaiementEnum] = None
    date_paiement: Optional[datetime] = None
    facture_url: Optional[str] = None


class AbonnementFacturationResponse(BaseModel):
    id: int
    organisation_id: int
    periode: str
    montant: Decimal
    devise: str
    statut_paiement: StatutPaiementEnum
    date_echeance: Optional[date] = None
    date_paiement: Optional[datetime] = None
    facture_url: Optional[str] = None
    date_creation: Optional[datetime] = None

    # Champs calculés / joints
    organisation_nom: Optional[str] = None
    est_en_retard: bool = False

    model_config = ConfigDict(from_attributes=True)