from pydantic import BaseModel, Field, ConfigDict, computed_field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class StatutBesoinEnum(str, Enum):
    BROUILLON = "BROUILLON"
    EN_VALIDATION = "EN_VALIDATION"
    DG_VALIDE = "DG_VALIDE"
    COMPTABLE_VALIDE = "COMPTABLE_VALIDE"
    CAISSE_VALIDE = "CAISSE_VALIDE"
    REJETE = "REJETE"
    APPROUVEE = "APPROUVEE"
    ATTENTE_STOCK = "ATTENTE_STOCK"

class LigneBesoinCreate(BaseModel):
    id_piece: int
    quantite: int = Field(..., ge=1)

class BesoinCreate(BaseModel):
    id_panne: int
    observations: Optional[str] = None
    lignes: List[LigneBesoinCreate] = Field(..., min_length=1)

class BesoinUpdate(BaseModel):
    observations: Optional[str] = None
    statut: Optional[StatutBesoinEnum] = None

class LigneBesoinResponse(BaseModel):
    id_ligne: int
    id_piece: int
    quantite: int
    prix_unitaire: float
    prix_total: float
    
    # ✅ Champs calculés via computed_field pour accéder aux données de la pièce
    @computed_field
    @property
    def reference_piece(self) -> Optional[str]:
        if hasattr(self, 'piece') and self.piece:
            return self.piece.reference
        return None
    
    @computed_field
    @property
    def designation_piece(self) -> Optional[str]:
        if hasattr(self, 'piece') and self.piece:
            return self.piece.designation
        return None

    model_config = ConfigDict(from_attributes=True)

class BesoinResponse(BaseModel):
    id_besoin: int
    id_panne: int
    numero_demande: str
    date_creation: datetime
    montant_total: float
    statut: StatutBesoinEnum
    observations: Optional[str] = None
    lignes: List[LigneBesoinResponse]
    
    model_config = ConfigDict(from_attributes=True)

class AjoutLigneRequest(BaseModel):
    id_piece: int = Field(..., gt=0)
    quantite: int = Field(..., ge=1)