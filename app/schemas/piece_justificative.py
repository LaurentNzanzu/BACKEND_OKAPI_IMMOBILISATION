from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional
from enum import Enum


class TypePieceJustificative(str, Enum):
    ACQUISITION = "ACQUISITION"
    FONDS = "FONDS"
    DECAISSEMENT = "DECAISSEMENT"
    AMORTISSEMENT = "AMORTISSEMENT"
    CESSION = "CESSION"
    MAINTENANCE = "MAINTENANCE"
    STOCK = "STOCK"
    INVENTAIRE = "INVENTAIRE"


class StatutPieceJustificative(str, Enum):
    BROUILLON = "BROUILLON"
    SOUMIS = "SOUMIS"
    VALIDE = "VALIDE"
    REJETE = "REJETE"
    ARCHIVE = "ARCHIVE"


class PieceJustificativeBase(BaseModel):
    type_piece: TypePieceJustificative
    titre: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    numero_reference: Optional[str] = Field(None, max_length=100)
    date_document: Optional[datetime] = None
    
    # Liens
    id_bien: Optional[int] = None
    id_besoin: Optional[int] = None
    id_amortissement: Optional[int] = None
    id_cession: Optional[int] = None
    id_maintenance: Optional[int] = None
    id_ecriture: Optional[int] = None


class PieceJustificativeCreate(PieceJustificativeBase):
    fichier_nom: str = Field(..., max_length=255)
    fichier_url: str = Field(..., max_length=500)
    fichier_taille: Optional[float] = None
    fichier_type: Optional[str] = None


class PieceJustificativeUpdate(BaseModel):
    titre: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    numero_reference: Optional[str] = Field(None, max_length=100)
    statut: Optional[StatutPieceJustificative] = None


class PieceJustificativeValidation(BaseModel):
    decision: str = Field(..., pattern="^(VALIDER|REJETER)$")
    motif: Optional[str] = Field(None, max_length=500)


class PieceJustificativeSignature(BaseModel):
    signature: str = Field(..., min_length=10, description="Signature électronique")


class PieceJustificativeResponse(BaseModel):
    id_piece: int
    type_piece: TypePieceJustificative
    statut: StatutPieceJustificative
    titre: str
    description: Optional[str] = None
    numero_reference: Optional[str] = None
    fichier_nom: str
    fichier_url: str
    fichier_taille: Optional[float] = None
    fichier_type: Optional[str] = None
    date_document: Optional[datetime] = None
    date_upload: datetime
    date_validation: Optional[datetime] = None
    est_signee: bool = False
    date_signature: Optional[datetime] = None
    signature_electronique: Optional[str] = None
    motif_rejet: Optional[str] = None
    
    # Liens
    id_bien: Optional[int] = None
    id_besoin: Optional[int] = None
    id_amortissement: Optional[int] = None
    id_cession: Optional[int] = None
    id_maintenance: Optional[int] = None
    id_ecriture: Optional[int] = None
    
    # Utilisateurs
    upload_par_id: Optional[int] = None
    valide_par_id: Optional[int] = None
    signe_par_id: Optional[int] = None
    upload_par_nom: Optional[str] = None
    valide_par_nom: Optional[str] = None
    signe_par_nom: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
