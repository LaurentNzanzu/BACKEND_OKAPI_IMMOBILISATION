# app/schemas/ecriture_comptable.py
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime
from typing import Optional
from enum import Enum


class StatutEcritureEnum(str, Enum):
    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"
    REJETEE = "REJETEE"
    MODIFIEE = "MODIFIEE"
    EN_ATTENTE_PAIEMENT = "EN_ATTENTE_PAIEMENT"
    EN_ATTENTE_FONDS = "EN_ATTENTE_FONDS"
    CAISSE_VALIDE = "CAISSE_VALIDE"
    DG_VALIDE = "DG_VALIDE"


class TypeOpEnum(str, Enum):
    DOTATION_AMORTISSEMENT = "DOTATION_AMORTISSEMENT"
    ACQUISITION = "ACQUISITION"
    CESSION = "CESSION"
    REPRISE = "REPRISE"
    REPRISE_DEPRECIATION = "REPRISE_DEPRECIATION"
    DEPRECIATION = "DEPRECIATION"
    DECAISSEMENT = "DECAISSEMENT"


class EcritureCreate(BaseModel):
    id_bien: int = Field(..., gt=0)
    id_amortissement: Optional[int] = Field(None, gt=0)
    type_operation: TypeOpEnum
    compte_debit: str = Field(..., min_length=3, max_length=20, description="Compte SYSCOHADA débité")
    compte_credit: str = Field(..., min_length=3, max_length=20, description="Compte SYSCOHADA crédité")
    montant: float = Field(..., gt=0, description="Montant strictement positif")
    piece_justificative: Optional[str] = Field(None, max_length=100)
    libelle: Optional[str] = Field(None, max_length=500)
    date_ecriture: datetime
    exercice: int = Field(..., ge=2000, le=2100)

    @field_validator('compte_debit', 'compte_credit')
    @classmethod
    def validate_compte_syscohada(cls, v):
        if not v or len(v.strip()) < 3:
            raise ValueError("Le compte SYSCOHADA doit avoir au moins 3 caractères")
        if not v.strip().isdigit():
            raise ValueError("Le compte SYSCOHADA doit être numérique")
        return v.strip()

    @model_validator(mode='after')
    def validate_equilibre(self):
        if self.compte_debit == self.compte_credit:
            raise ValueError("Les comptes débit et crédit doivent être différents")
        if self.compte_debit == self.compte_credit:
            # Les comptes sont déjà distincts
            pass
        return self


class EcritureResponse(BaseModel):
    id_ecriture: int
    id_bien: int
    type_operation: TypeOpEnum
    statut: Optional[StatutEcritureEnum] = None
    libelle: Optional[str]
    compte_debit: str
    compte_credit: str
    montant: float
    montant_original: Optional[float] = None 
    motif_modification: Optional[str] = None   
    validee: bool
    date_ecriture: datetime
    date_creation: Optional[datetime] = None
    date_validation: Optional[datetime] = None
    exercice: Optional[int] = None
    journal: Optional[str] = None
    periode_comptable: Optional[str] = None
    cree_par: Optional[int] = None
    valide_par: Optional[int] = None
    bien_designation: Optional[str] = None
    
    piece_justificative_url: Optional[str] = None
    statut_workflow: Optional[str] = None
    est_verrouillee: bool = False
    date_verification_caisse: Optional[datetime] = None
    date_validation_dg: Optional[datetime] = None
    workflow_etape: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def map_verrouille(cls, data):
        if hasattr(data, 'verrouille_definitivement'):
            setattr(data, 'est_verrouillee', getattr(data, 'verrouille_definitivement') or False)
        elif isinstance(data, dict):
            data['est_verrouillee'] = data.get('verrouille_definitivement') or False
        return data

    model_config = ConfigDict(from_attributes=True)