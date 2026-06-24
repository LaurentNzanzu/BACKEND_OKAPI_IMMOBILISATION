from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List

class ComposantBase(BaseModel):
    id_bien: int = Field(..., description="ID du bien parent")
    designation: str = Field(..., min_length=1, max_length=200, description="Désignation du composant")
    valeur: float = Field(..., gt=0, description="Valeur d'origine du composant")
    duree_vie_ans: int = Field(..., ge=1, le=50, description="Durée de vie en années")

class ComposantCreate(ComposantBase):
    date_remplacement: Optional[datetime] = None
    date_mise_en_service: Optional[datetime] = None

class ComposantUpdate(BaseModel):
    designation: Optional[str] = Field(None, min_length=1, max_length=200)
    valeur: Optional[float] = Field(None, gt=0)
    duree_vie_ans: Optional[int] = Field(None, ge=1, le=50)
    date_remplacement: Optional[datetime] = None
    date_mise_en_service: Optional[datetime] = None

class ComposantResponse(ComposantBase):
    id_composant: int
    date_remplacement: Optional[datetime] = None
    date_creation: datetime

    model_config = ConfigDict(from_attributes=True)

class ComposantListResponse(BaseModel):
    total: int
    composants: List[ComposantResponse]