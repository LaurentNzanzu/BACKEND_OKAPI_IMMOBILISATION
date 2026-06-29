# app/schemas/besoin.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from .piece_rechange import PieceRechangeResponse


class LigneBesoinCreate(BaseModel):
    id_piece: Optional[int] = Field(None, gt=0)
    designation: Optional[str] = None
    prix_unitaire: Optional[float] = Field(None, gt=0)
    quantite: int = Field(..., gt=0)

    @model_validator(mode='after')
    def check_hors_catalogue_fields(self):
        if self.id_piece is None:
            if not self.designation or not str(self.designation).strip():
                raise ValueError('La désignation est obligatoire pour une pièce hors catalogue')
            if self.prix_unitaire is None or self.prix_unitaire <= 0:
                raise ValueError('Le prix unitaire est obligatoire pour une pièce hors catalogue')
        return self


class LigneBesoinRead(BaseModel):
    id_ligne: int
    id_besoin: int
    id_piece: int
    quantite: int
    prix_unitaire: float
    prix_total: float
    est_hors_catalogue: bool
    piece: Optional[PieceRechangeResponse] = None

    class Config:
        from_attributes = True


class BesoinCreate(BaseModel):
    id_panne: int = Field(..., gt=0)
    id_budget: Optional[int] = Field(None, description="ID du budget associé")
    centre_cout: Optional[str] = Field(None, description="Code ou nom du centre de coût")
    date_limite: Optional[datetime] = Field(None, description="Date limite de traitement du besoin")
    lignes: List[LigneBesoinCreate] = Field(..., min_length=1)

    @model_validator(mode='after')
    def validate_dates(self):
        if self.date_limite:
            now = datetime.now()
            if self.date_limite < now:
                raise ValueError("La date limite ne peut être dans le passé")
        return self


class BesoinUpdate(BaseModel):
    statut: Optional[str] = None
    id_budget: Optional[int] = None
    centre_cout: Optional[str] = None


class BesoinResponse(BaseModel):
    id_besoin: int
    id_panne: int
    numero_demande: str
    montant_total: float
    statut: str
    id_budget: Optional[int] = None
    centre_cout: Optional[str] = None
    date_creation: datetime
    date_limite: Optional[datetime] = None
    lignes: List[LigneBesoinRead] = []

    class Config:
        from_attributes = True


class AjoutLigneRequest(BaseModel):
    id_piece: int = Field(..., gt=0)
    quantite: int = Field(..., gt=0)


class AjoutLigneHorsCatalogueRequest(BaseModel):
    designation: str = Field(..., min_length=1)
    prix_unitaire: float = Field(..., gt=0)
    quantite: int = Field(..., gt=0)