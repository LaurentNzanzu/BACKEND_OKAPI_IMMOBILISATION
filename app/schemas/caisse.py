# backend/app/schemas/caisse.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CaisseBase(BaseModel):
    solde_physique: float = 0.0
    solde_theorique: float = 0.0
    devise: str = "FCFA"
    statut: str = "ACTIF"


class CaisseCreate(CaisseBase):
    pass


class CaisseUpdate(BaseModel):
    solde_physique: Optional[float] = None
    solde_theorique: Optional[float] = None
    devise: Optional[str] = None
    statut: Optional[str] = None


class CaisseResponse(CaisseBase):
    id_caisse: int
    dernier_rapprochement: Optional[datetime] = None

    class Config:
        from_attributes = True


class TresorerieVerificationResponse(BaseModel):
    est_suffisante: bool
    solde_disponible: float
    message: str
