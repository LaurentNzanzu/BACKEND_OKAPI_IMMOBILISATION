# backend/app/schemas/plan_comptable.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime

class PlanComptableBase(BaseModel):
    numero: str = Field(..., min_length=1, max_length=10)
    libelle: str = Field(..., min_length=1, max_length=255)
    classe: str = Field(..., min_length=1, max_length=1)
    type: str = Field(..., pattern="^(actif|passif|charge|produit)$")
    est_actif: bool = True

class PlanComptableCreate(PlanComptableBase):
    pass

class PlanComptableUpdate(BaseModel):
    numero: Optional[str] = Field(None, min_length=1, max_length=10)
    libelle: Optional[str] = Field(None, min_length=1, max_length=255)
    classe: Optional[str] = Field(None, min_length=1, max_length=1)
    type: Optional[str] = Field(None, pattern="^(actif|passif|charge|produit)$")
    est_actif: Optional[bool] = None

class PlanComptableResponse(PlanComptableBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class PlanComptableListResponse(BaseModel):
    total: int
    comptes: list[PlanComptableResponse]