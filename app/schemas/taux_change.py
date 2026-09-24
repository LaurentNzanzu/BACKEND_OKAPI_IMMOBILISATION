from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List


class TauxChangeBase(BaseModel):
    """Champs de base partagés."""
    devise_source: str = Field(..., min_length=3, max_length=3, description="Ex: USD")
    devise_cible: str = Field(..., min_length=3, max_length=3, description="Ex: CDF")
    taux: Decimal = Field(..., gt=0, description="1 devise_source = X devise_cible")
    date_taux: Optional[date] = None
    source: Optional[str] = Field(default="MANUEL", max_length=50)

    @field_validator("devise_source", "devise_cible")
    @classmethod
    def upper_devise(cls, v: str) -> str:
        return v.strip().upper()


class TauxChangeCreate(TauxChangeBase):
    """Payload pour créer/mettre à jour un taux."""
    organisation_id: int = Field(..., gt=0)


class TauxChangeUpdate(BaseModel):
    """Payload pour modifier un taux existant."""
    taux: Optional[Decimal] = Field(None, gt=0)
    source: Optional[str] = Field(None, max_length=50)


class TauxChangeResponse(BaseModel):
    """Réponse d'un taux."""
    id: int
    organisation_id: int
    devise_source: str
    devise_cible: str
    taux: Decimal
    date_taux: date
    source: Optional[str] = None
    date_creation: Optional[datetime] = None
    utilisateur_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class TauxChangeListResponse(BaseModel):
    """Liste paginée de taux."""
    items: List[TauxChangeResponse] = Field(default_factory=list)
    total: int = 0


class ConversionRequest(BaseModel):
    """Payload pour demander une conversion."""
    organisation_id: int = Field(..., gt=0)
    montant: Decimal = Field(..., ge=0)
    devise_source: str = Field(..., min_length=3, max_length=3)
    devise_cible: str = Field(..., min_length=3, max_length=3)
    date_reference: Optional[date] = None

    @field_validator("devise_source", "devise_cible")
    @classmethod
    def upper_devise(cls, v: str) -> str:
        return v.strip().upper()


class ConversionResponse(BaseModel):
    """Réponse d'une conversion."""
    montant_origine: Decimal
    montant_converti: Decimal
    taux: Decimal
    devise_source: str
    devise_cible: str
    date_taux: Optional[str] = None
    source: Optional[str] = None