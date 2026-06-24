# backend/app/schemas/fournisseur.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class FournisseurBase(BaseModel):
    nom: str
    adresse: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    numero_contribuable: Optional[str] = None

class FournisseurCreate(FournisseurBase):
    pass

class FournisseurUpdate(BaseModel):
    nom: Optional[str] = None
    adresse: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    numero_contribuable: Optional[str] = None

class FournisseurResponse(FournisseurBase):
    id: int
    date_creation: datetime
    
    class Config:
        from_attributes = True