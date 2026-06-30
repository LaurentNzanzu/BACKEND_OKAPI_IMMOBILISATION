from pydantic import BaseModel, Field, model_validator
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
    AUTRE = "AUTRE"


class DemandeurBrief(BaseModel):
    prenom: str
    nom: str


class PanneBase(BaseModel):
    id_bien: int
    type_panne: TypePanneEnum = TypePanneEnum.AUTRE
    type_panne_personnalise: Optional[str] = Field(None, max_length=200)
    priorite: PrioritePanneEnum = PrioritePanneEnum.MOYENNE
    diagnostic: Optional[str] = Field(None, min_length=5, max_length=1000)

    @model_validator(mode="after")
    def validate_type_autre(self):
        if self.type_panne == TypePanneEnum.AUTRE:
            if not self.type_panne_personnalise or not self.type_panne_personnalise.strip():
                raise ValueError(
                    "Le champ type_panne_personnalise est obligatoire lorsque le type de panne est AUTRE."
                )
        return self


class PanneCreate(PanneBase):
    pass


class PanneUpdate(BaseModel):
    type_panne: Optional[TypePanneEnum] = None
    type_panne_personnalise: Optional[str] = Field(None, max_length=200)
    priorite: Optional[PrioritePanneEnum] = None
    statut: Optional[StatutPanneEnum] = None
    diagnostic: Optional[str] = None
    solution_apportee: Optional[str] = None
    cout_total_reparation: Optional[float] = None


class PanneResponse(BaseModel):
    id_panne: int
    id_bien: int
    bien_designation: Optional[str] = None
    demandeur: DemandeurBrief
    type_panne: TypePanneEnum
    type_panne_personnalise: Optional[str] = None
    priorite: PrioritePanneEnum
    diagnostic: Optional[str] = None
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
