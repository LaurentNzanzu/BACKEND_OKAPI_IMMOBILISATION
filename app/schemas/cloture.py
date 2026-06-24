# backend/app/schemas/cloture.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum

class MethodeAmortissementEnum(str, Enum):
    LINEAIRE = "LINEAIRE"
    DEGRESSIF = "DEGRESSIF"
    COMPOSANTS = "COMPOSANTS"
    UNITE_PRODUCTION = "UNITE_PRODUCTION"
    SPECIFIQUE_OKAPI = "SPECIFIQUE_OKAPI"

class CloturePayload(BaseModel):
    exercice: int = Field(..., description="Année à clôturer", ge=2000, le=2100)
    categorie: Optional[str] = Field(None, description="Filtre par catégorie de bien (vehicule, machine, ordinateur, mobilier)")
    methode_forcee: Optional[MethodeAmortissementEnum] = Field(None, description="Méthode d'amortissement à forcer (null = automatique)")
    biens_selectionnes: Optional[List[int]] = Field(None, description="Liste des IDs de biens à traiter (null = tous)")
    
    @field_validator('categorie')
    def validate_categorie(cls, v):
        if v is not None and v not in ['vehicule', 'machine', 'ordinateur', 'mobilier', 'autre']:
            raise ValueError(f"Catégorie invalide: {v}")
        return v

# backend/app/schemas/cloture.py (à modifier)

class BienPrevisualisation(BaseModel):
    id_bien: int
    designation: str
    categorie: str
    methode_actuelle: str
    montant_estime: float
    prix_acquisition: float
    cumul_amortissement: float
    vnc_actuelle: float
    date_acquisition: Optional[datetime] = None 
    exercice: int
    est_eligible: bool = True
    raison_non_eligibilite: Optional[str] = None
class PrevisualisationClotureResponse(BaseModel):
    exercice: int
    total_biens: int
    total_eligibles: int
    total_montant_estime: float
    biens: List[BienPrevisualisation]
    filtres_appliques: dict

class RapportCloture(BaseModel):
    exercice: int
    total_biens_traites: int
    amortissements_crees: List[dict]
    ecritures_dotations_generees: int
    erreurs: List[dict]
    resume_par_categorie: dict
    resume_par_methode: dict
    date_execution: datetime = Field(default_factory=datetime.utcnow)