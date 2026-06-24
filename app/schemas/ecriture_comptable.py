from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from enum import Enum

class StatutEcritureEnum(str, Enum):
    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"
    REJETEE = "REJETEE"
    MODIFIEE = "MODIFIEE"

class TypeOpEnum(str, Enum):
    DOTATION_AMORTISSEMENT = "DOTATION_AMORTISSEMENT"
    ACQUISITION = "ACQUISITION"
    CESSION = "CESSION"
    REPRISE = "REPRISE"
    REPRISE_DEPRECIATION = "REPRISE_DEPRECIATION"
    DEPRECIATION = "DEPRECIATION"

class EcritureCreate(BaseModel):
    id_bien: int
    id_amortissement: Optional[int] = None
    type_operation: TypeOpEnum
    compte_debit: str
    compte_credit: str
    montant: float
    piece_justificative: Optional[str] = None
    libelle: Optional[str] = None
    date_ecriture: datetime
    exercice: int

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
    date_validation: Optional[datetime]
    exercice: Optional[int] = None
    journal: Optional[str] = None
    periode_comptable: Optional[str] = None
    cree_par: Optional[int] = None
    valide_par: Optional[int] = None
    bien_designation: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)