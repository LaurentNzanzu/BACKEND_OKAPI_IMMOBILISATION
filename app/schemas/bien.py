# backend/app/schemas/bien.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

class EtatBienEnum(str, Enum):
    NEUF = "NEUF"
    BON = "BON"
    USAGE = "USAGE"
    PANNE = "PANNE"
    REFORME = "REFORME"
    MAINTENANCE = "MAINTENANCE"

class ModePaiementEnum(str, Enum):
    CREDIT = "credit"
    COMPTANT = "comptant"

class BienBase(BaseModel):
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = Field(None, ge=0)
    etat: EtatBienEnum = EtatBienEnum.NEUF
    localisation: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None

class BienCreate(BienBase):
    type_bien: str  # "vehicule", "machine", "ordinateur"
    date_acquisition: date  # requis à la création
    
    # === NOUVEAUX CHAMPS PHASE 1 ===
    mode_paiement: ModePaiementEnum = ModePaiementEnum.CREDIT
    fournisseur_id: Optional[int] = Field(None, description="ID du fournisseur (requis si mode_paiement=credit)")
    
    @field_validator('fournisseur_id')
    def validate_fournisseur(cls, v, info):
        mode = info.data.get('mode_paiement')
        if mode == ModePaiementEnum.CREDIT and v is None:
            raise ValueError('Le fournisseur est requis pour un paiement à crédit')
        return v
    
    # Champs spécifiques véhicules
    type_vehicule: Optional[str] = None
    marque: Optional[str] = None
    modele: Optional[str] = None
    immatriculation: Optional[str] = None
    poids: Optional[float] = None
    dimension: Optional[str] = None
    type_carburant: Optional[str] = None
    consommation_carburant: Optional[float] = None
    consommation_huile: Optional[float] = None
    type_propulsion: Optional[str] = None
    
    # Champs spécifiques machines
    numero_serie: Optional[str] = None
    fabricant: Optional[str] = None
    puissance: Optional[float] = None
    type_alimentation: Optional[str] = None
    tension_normal: Optional[str] = None
    service_affecte: Optional[str] = None
    responsable: Optional[str] = None
    consommation_elec: Optional[float] = None
    frequence_maintenance: Optional[str] = None
    
    # Champs spécifiques ordinateurs
    processeur: Optional[str] = None
    ram: Optional[str] = None
    stockage: Optional[str] = None
    adresse_ip: Optional[str] = None
    utilisateur_affecte: Optional[str] = None

class BienUpdate(BaseModel):
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = None
    etat: Optional[EtatBienEnum] = None
    localisation: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    
    # Nouveaux champs
    mode_paiement: Optional[ModePaiementEnum] = None
    fournisseur_id: Optional[int] = None
    
    # Champs spécifiques (mêmes que BienCreate mais optionnels)
    type_vehicule: Optional[str] = None
    marque: Optional[str] = None
    modele: Optional[str] = None
    immatriculation: Optional[str] = None
    poids: Optional[float] = None
    dimension: Optional[str] = None
    type_carburant: Optional[str] = None
    consommation_carburant: Optional[float] = None
    consommation_huile: Optional[float] = None
    type_propulsion: Optional[str] = None
    
    numero_serie: Optional[str] = None
    fabricant: Optional[str] = None
    puissance: Optional[float] = None
    type_alimentation: Optional[str] = None
    tension_normal: Optional[str] = None
    service_affecte: Optional[str] = None
    responsable: Optional[str] = None
    consommation_elec: Optional[float] = None
    frequence_maintenance: Optional[str] = None
    
    processeur: Optional[str] = None
    ram: Optional[str] = None
    stockage: Optional[str] = None
    adresse_ip: Optional[str] = None
    utilisateur_affecte: Optional[str] = None

class BienResponse(BienBase):
    id_bien: int
    qr_code: str
    date_creation: datetime
    type_bien: str
    statut_comptable: Optional[str] = "ACTIF"
    cumul_amortissement: Optional[Decimal] = 0
    cumul_depreciation: Optional[Decimal] = 0
    
    # NOUVEAUX CHAMPS
    mode_paiement: str
    fournisseur_id: Optional[int] = None
    
    # Champs spécifiques selon le type
    type_vehicule: Optional[str] = None
    immatriculation: Optional[str] = None
    numero_serie: Optional[str] = None
    fabricant: Optional[str] = None
    processeur: Optional[str] = None
    
    class Config:
        from_attributes = True

class BienListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    biens: List[BienResponse]