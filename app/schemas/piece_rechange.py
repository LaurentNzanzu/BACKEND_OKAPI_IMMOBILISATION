from pydantic import BaseModel, Field, field_validator, computed_field
from typing import Optional
from datetime import datetime
from enum import Enum


class TypeCompatibleEnum(str, Enum):
    VEHICULE = "VEHICULE"
    ORDINATEUR = "ORDINATEUR"
    MACHINE_PRODUCTION = "MACHINE_PRODUCTION"


class PieceRechangeBase(BaseModel):
    numero_serie: Optional[str] = Field(None, max_length=50)
    designation: str = Field(..., min_length=1, max_length=200)
    prix_achat: float = Field(..., gt=0)
    prix_vente: Optional[float] = Field(None, gt=0)
    compatible_avec: TypeCompatibleEnum
    fournisseur: Optional[str] = Field(None, max_length=200)

    @field_validator('numero_serie')
    @classmethod
    def validate_numero_serie(cls, v: str) -> str:
        """Valide le numéro de série : accepte chiffres uniquement OU format HC-"""
        if v:
            # Accepter les formats HC-... (pièces hors catalogue)
            if v.startswith('HC-'):
                return v
            # Accepter les formats purement numériques (pièces normales)
            if not v.isdigit():
                raise ValueError('Le numéro de série doit contenir uniquement des chiffres ou commencer par HC-')
        return v


class PieceRechangeCreate(PieceRechangeBase):
    stock_actuel: int = Field(0, ge=0)
    stock_minimum: int = Field(5, ge=1)


class PieceRechangeUpdate(BaseModel):
    numero_serie: Optional[str] = Field(None, max_length=50)
    designation: Optional[str] = Field(None, min_length=1, max_length=200)
    prix_achat: Optional[float] = Field(None, gt=0)
    prix_vente: Optional[float] = Field(None, gt=0)
    stock_actuel: Optional[int] = Field(None, ge=0)
    stock_minimum: Optional[int] = Field(None, ge=1)
    compatible_avec: Optional[TypeCompatibleEnum] = None
    fournisseur: Optional[str] = Field(None, max_length=200)
    est_active: Optional[bool] = None


class PieceRechangeResponse(PieceRechangeBase):
    id_piece: int
    stock_actuel: int
    stock_minimum: int
    est_active: bool
    date_creation: datetime
    compatible_display: Optional[str] = None

    @computed_field
    @property
    def reference(self) -> str:
        """Retourne le numéro de série comme référence pour le scan"""
        return self.numero_serie or f"PCE-{self.id_piece}"

    class Config:
        from_attributes = True