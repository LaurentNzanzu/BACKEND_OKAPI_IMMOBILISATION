from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

class RepriseDepreciationPayload(BaseModel):
    bien_id: int = Field(..., description="ID du bien")
    montant_reprise: float = Field(..., gt=0, description="Montant à reprendre")
    motif: str = Field(..., min_length=3, max_length=500, description="Motif de la reprise")
    depreciation_id: Optional[int] = Field(None, description="ID de l'amortissement associé")
    
    @field_validator('montant_reprise')
    def validate_montant(cls, v):
        if v <= 0:
            raise ValueError("Le montant de la reprise doit être supérieur à 0")
        return v

class RepriseDepreciationResponse(BaseModel):
    ecriture_id: int
    nouveau_cumul_depreciation: float
    statut_comptable: str
    message: str

class DepreciationItem(BaseModel):
    id_amortissement: int
    date_depreciation: Optional[str]
    montant_depreciation: float
    valeur_actualisee: float
    exercice: int

class RepriseItem(BaseModel):
    id_ecriture: int
    date_ecriture: Optional[str]
    montant: float
    libelle: str
    compte_debit: str
    compte_credit: str

class HistoriqueDepreciationsResponse(BaseModel):
    cumul_depreciation: float
    statut_comptable: str
    depreciations: list[DepreciationItem]
    reprises: list[RepriseItem]