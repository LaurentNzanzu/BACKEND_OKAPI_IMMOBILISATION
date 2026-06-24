from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class PrioritePanneEnum(str, Enum):
    BASSE = "BASSE"
    MOYENNE = "MOYENNE"
    HAUTE = "HAUTE"
    CRITIQUE = "CRITIQUE"

class StatutPanneEnum(str, Enum):
    DECLAREE = "DECLAREE"
    DIAGNOSTIQUEE = "DIAGNOSTIQUEE"
    EN_ATTENTE_PIECES = "EN_ATTENTE_PIECES"
    EN_VALIDATION = "EN_VALIDATION"
    EN_COURS = "EN_COURS"
    EN_TEST = "EN_TEST"
    TERMINEE = "TERMINEE"
    ANNULEE = "ANNULEE"

class TypePanneEnum(str, Enum):
    MECANIQUE = "MECANIQUE"
    ELECTRIQUE = "ELECTRIQUE"
    ELECTRONIQUE = "ELECTRONIQUE"
    LOGICIELLE = "LOGICIELLE"
    STRUCTURELLE = "STRUCTURELLE"
    AUTRE = "AUTRE"

class PanneBase(BaseModel):
    id_bien: int
    type_panne: TypePanneEnum = TypePanneEnum.AUTRE
    priorite: PrioritePanneEnum = PrioritePanneEnum.MOYENNE
    description: str = Field(..., min_length=5, max_length=1000)
    diagnostic: Optional[str] = None

class PanneCreate(PanneBase):
    pass

class PanneUpdate(BaseModel):
    type_panne: Optional[TypePanneEnum] = None
    priorite: Optional[PrioritePanneEnum] = None
    statut: Optional[StatutPanneEnum] = None
    diagnostic: Optional[str] = None
    solution_apportee: Optional[str] = None
    cout_total_reparation: Optional[float] = None

class PanneResponse(PanneBase):
    id_panne: int
    id_technicien: int
    date_declaration: datetime
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None
    statut: StatutPanneEnum
    cout_total_reparation: float
    solution_apportee: Optional[str] = None
    duree_jours: Optional[int] = None
    bien_context: Optional[dict] = None

    class Config:
        from_attributes = True