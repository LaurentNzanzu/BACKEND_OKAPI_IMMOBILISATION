# app/schemas/base.py
from pydantic import BaseModel, Field, ConfigDict, field_validator
from decimal import Decimal
from datetime import datetime
from typing import Optional, TypeVar, Generic, List

T = TypeVar('T')


class BaseSchema(BaseModel):
    """Schéma de base avec configuration commune."""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        json_encoders={
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat()
        }
    )


class TimestampMixin(BaseModel):
    """Mixin pour les champs de timestamp automatiques."""
    date_creation: Optional[datetime] = Field(default=None, description="Date de création")
    date_modification: Optional[datetime] = Field(default=None, description="Date de dernière modification")


class IdentifiantMixin(BaseModel):
    """Mixin pour l'identifiant standard."""
    id: int = Field(..., gt=0, description="Identifiant unique")


class PaginatedResponse(BaseSchema, Generic[T]):
    """Schéma de réponse paginé standard."""
    total: int = Field(..., ge=0, description="Nombre total d'éléments")
    page: int = Field(..., ge=1, description="Page actuelle")
    page_size: int = Field(..., ge=1, le=500, description="Éléments par page")
    items: List[T] = Field(default_factory=list, description="Liste des éléments")

    @field_validator('page_size')
    @classmethod
    def validate_page_size(cls, v):
        if v > 500:
            raise ValueError("La taille de page ne peut dépasser 500")
        return v