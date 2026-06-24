from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List
from enum import Enum


class StatutFournitureEnum(str, Enum):
    EN_ATTENTE = "EN_ATTENTE"
    FOURNIE = "FOURNIE"
    PARTIELLE = "PARTIELLE"
    REFUSEE = "REFUSEE"
    ANNULEE = "ANNULEE"


class FournitureValiderRequest(BaseModel):
    quantite_fournie: int = Field(..., gt=0)
    commentaire: Optional[str] = None


class FournitureRefuserRequest(BaseModel):
    commentaire: str = Field(..., min_length=3)


class FournitureResponse(BaseModel):
    id_fourniture: int
    id_besoin: int
    id_piece: int
    quantite_demandee: int
    quantite_fournie: Optional[int] = None
    date_fourniture: Optional[datetime] = None
    id_magasinier: Optional[int] = None
    statut: StatutFournitureEnum
    commentaire: Optional[str] = None
    date_creation: Optional[datetime] = None
    date_modification: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FournitureStatistiques(BaseModel):
    total: int
    en_attente: int
    fournies: int
    partielles: int
    refusees: int
    annulees: int
    taux_completion: float
