# backend/app/schemas/mouvement_caisse.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List


class MouvementCaisseBase(BaseModel):
    type_mouvement: str  # 'ENTREE' ou 'SORTIE'
    montant: float
    motif: str
    origine_type: str  # 'BESOIN', 'MAINTENANCE', 'STOCK', 'ACQUISITION', 'CESSION', 'AMORTISSEMENT'
    origine_id: int
    mode_reglement: Optional[str] = "ESPECES"
    beneficiaire: Optional[str] = None


class MouvementCaisseCreate(MouvementCaisseBase):
    id_caisse: int


class MouvementCaisseUpdate(BaseModel):
    statut: Optional[str] = None
    piece_jointe_url: Optional[str] = None
    valide_par: Optional[int] = None


class MouvementCaisseResponse(MouvementCaisseBase):
    id_mouvement: int
    id_caisse: int
    numero_piece: str
    date_mouvement: datetime
    solde_avant: float
    solde_apres: float
    piece_jointe_url: Optional[str] = None
    statut: str
    valide_par: Optional[int] = None
    date_validation: Optional[datetime] = None
    caisse_nom: Optional[str] = "Caisse Principale"

    model_config = ConfigDict(from_attributes=True)


class MouvementCaisseListResponse(BaseModel):
    items: List[MouvementCaisseResponse]
    total: int
    page: int
    pages: int


class ApprovisionnementCaisseRequest(BaseModel):
    montant: float
    motif: str
    mode_reglement: Optional[str] = "ESPECES"


class ValidationMouvementRequest(BaseModel):
    statut: str
    commentaire: Optional[str] = None


class SignatureDGRequest(BaseModel):
    approuve: bool
    motif: Optional[str] = None
    commentaire: Optional[str] = None
