# backend/app/schemas/piece_justificative.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class PieceJustificativeBase(BaseModel):
    type_document: str  # 'BEC' ou 'BSC'
    numero_document: str
    url_fichier: str


class PieceJustificativeCreate(PieceJustificativeBase):
    id_mouvement: int


class PieceJustificativeResponse(PieceJustificativeBase):
    id_piece: int
    id_mouvement: int
    signature_caissier: bool
    signature_dg: bool
    date_signature_caissier: Optional[datetime] = None
    date_signature_dg: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PieceJustificativeSignRequest(BaseModel):
    signature_caissier: Optional[bool] = None
    signature_dg: Optional[bool] = None
