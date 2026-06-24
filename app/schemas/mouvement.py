# backend/app/schemas/mouvement.py
from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationInfo
from datetime import datetime
from typing import Optional, List, Literal
from enum import Enum

class TypeMouvementEnum(str, Enum):
    TRANSFERT = "TRANSFERT"
    SORTIE = "SORTIE"
    CESSION = "CESSION"
    AFFECTATION = "AFFECTATION"
    RETOUR = "RETOUR"

class MouvementBase(BaseModel):
    id_bien: int = Field(..., description="ID du bien concerné")
    type_mouvement: TypeMouvementEnum
    date_mouvement: Optional[datetime] = Field(default=None, description="Date du mouvement (auto si null)")
    localisation_source: Optional[str] = Field(None, max_length=200)
    localisation_destination: Optional[str] = Field(None, max_length=200)
    responsable_sortie: Optional[str] = Field(None, max_length=200)
    raison: str = Field(..., min_length=3, max_length=1000, description="Raison du mouvement")  # ✅ 3 caractères minimum
    piece_justificative: Optional[str] = Field(None, max_length=500)
    prix_vente: Optional[float] = Field(None, gt=0, description="Prix de vente (CESSION)")
    acheteur: Optional[str] = Field(None, max_length=255)
    mode_reglement: Optional[str] = Field(None, max_length=50)
    type_cession: Optional[Literal["courante", "non_courante"]] = "courante"

class MouvementCreate(MouvementBase):
    @field_validator('date_mouvement')
    @classmethod
    def validate_date_not_future(cls, v: Optional[datetime], info: ValidationInfo) -> Optional[datetime]:
        if v is None:
            return v
        from datetime import datetime, timedelta
        if v > datetime.utcnow() + timedelta(hours=1):
            # Récupérer le type_mouvement des données validées
            data = info.data
            if isinstance(data, dict) and data.get('type_mouvement') != TypeMouvementEnum.AFFECTATION:
                raise ValueError("La date du mouvement ne peut pas être dans le futur")
        return v
    
    @field_validator('responsable_sortie')
    @classmethod
    def validate_responsable_for_sortie(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        data = info.data
        if isinstance(data, dict):
            type_mvt = data.get('type_mouvement')
            if type_mvt in [TypeMouvementEnum.CESSION, TypeMouvementEnum.SORTIE] and not v:
                raise ValueError("Le responsable de sortie est obligatoire pour une CESSION ou SORTIE")
        return v

class MouvementUpdate(BaseModel):
    raison: Optional[str] = Field(None, min_length=3, max_length=1000)
    piece_justificative: Optional[str] = Field(None, max_length=500)

class MouvementResponse(BaseModel):
    id_mouvement: int
    id_bien: int
    id_utilisateur: int
    type_mouvement: TypeMouvementEnum
    date_mouvement: datetime
    localisation_source: Optional[str]
    localisation_destination: Optional[str]
    responsable_sortie: Optional[str]
    raison: str
    piece_justificative: Optional[str]
    created_at: datetime
    
    bien_designation: Optional[str] = None
    utilisateur_nom: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class MouvementListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    mouvements: List[MouvementResponse]