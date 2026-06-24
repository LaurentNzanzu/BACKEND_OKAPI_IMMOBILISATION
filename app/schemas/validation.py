from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum

class OrdreValidationEnum(str, Enum):
    DG = "DG"
    COMPTABLE = "COMPTABLE"
    CAISSE = "CAISSE"

class DecisionValidationEnum(str, Enum):
    APPROUVE = "APPROUVE"
    REJETE = "REJETE"
    EN_ATTENTE = "EN_ATTENTE"

class ValidationRequest(BaseModel):
    decision: DecisionValidationEnum
    commentaire: Optional[str] = None

class ValidationResponse(BaseModel):
    id_validation: int
    id_validateur: int
    nom_validateur: Optional[str] = None
    ordre_validateur: OrdreValidationEnum
    decision: DecisionValidationEnum
    date_validation: datetime
    commentaire: Optional[str] = None

    class Config:
        from_attributes = True