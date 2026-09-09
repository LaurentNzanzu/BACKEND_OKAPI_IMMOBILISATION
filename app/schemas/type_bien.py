# backend/app/schemas/type_bien.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


class ChampSpecifiqueSchema(BaseModel):
    """Schéma pour un champ spécifique d'un type de bien"""
    nom: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="Type de champ: text, number, date, select, boolean")
    obligatoire: bool = False
    options: Optional[List[str]] = Field(None, description="Options pour le type 'select'")
    valeur_par_defaut: Optional[Any] = None
    aide: Optional[str] = None

    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        types_valides = ["text", "number", "date", "select", "boolean", "textarea", "email", "tel"]
        if v not in types_valides:
            raise ValueError(f"Type de champ invalide. Types valides: {types_valides}")
        return v


class TypeBienBase(BaseModel):
    """Schéma de base pour un type de bien"""
    libelle: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=20, pattern=r'^[A-Z0-9_]+$')
    compte_comptable: str = Field(default="2440", min_length=3, max_length=10)
    champs_specifiques: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    description: Optional[str] = Field(None, max_length=500)
    est_actif: bool = True


class TypeBienCreate(TypeBienBase):
    """Schéma pour la création d'un type de bien"""
    
    @field_validator('code')
    @classmethod
    def validate_code(cls, v):
        if not v.isupper() and not v.isdigit() and '_' not in v:
            raise ValueError("Le code doit être en majuscules, contenir des chiffres ou des underscores")
        return v

    @field_validator('champs_specifiques')
    @classmethod
    def validate_champs(cls, v):
        if v:
            for champ in v:
                if not isinstance(champ, dict):
                    raise ValueError("Chaque champ doit être un dictionnaire")
                if 'nom' not in champ:
                    raise ValueError("Chaque champ doit avoir un 'nom'")
                if 'type' not in champ:
                    raise ValueError("Chaque champ doit avoir un 'type'")
        return v


class TypeBienUpdate(BaseModel):
    """Schéma pour la mise à jour d'un type de bien"""
    libelle: Optional[str] = Field(None, min_length=2, max_length=100)
    code: Optional[str] = Field(None, min_length=2, max_length=20, pattern=r'^[A-Z0-9_]+$')
    compte_comptable: Optional[str] = Field(None, min_length=3, max_length=10)
    champs_specifiques: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = Field(None, max_length=500)
    est_actif: Optional[bool] = None

    @field_validator('champs_specifiques')
    @classmethod
    def validate_champs_update(cls, v):
        if v is not None:
            for champ in v:
                if not isinstance(champ, dict):
                    raise ValueError("Chaque champ doit être un dictionnaire")
                if 'nom' not in champ:
                    raise ValueError("Chaque champ doit avoir un 'nom'")
                if 'type' not in champ:
                    raise ValueError("Chaque champ doit avoir un 'type'")
        return v


class TypeBienResponse(TypeBienBase):
    """Schéma de réponse pour un type de bien"""
    id: int
    date_creation: datetime
    date_modification: Optional[datetime] = None

    class Config:
        from_attributes = True


class TypeBienListResponse(BaseModel):
    """Schéma pour la liste des types de biens"""
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=500)
    types: List[TypeBienResponse] = Field(default_factory=list)


# Types de biens pré-définis pour la migration
TYPES_BIENS_PREDEFINIS = [
    {
        "libelle": "Véhicule",
        "code": "VEHICULE",
        "compte_comptable": "2445",
        "champs_specifiques": [
            {"nom": "type_vehicule", "type": "text", "obligatoire": False},
            {"nom": "marque", "type": "text", "obligatoire": True},
            {"nom": "modele", "type": "text", "obligatoire": False},
            {"nom": "immatriculation", "type": "text", "obligatoire": False},
            {"nom": "poids", "type": "number", "obligatoire": False},
            {"nom": "dimension", "type": "text", "obligatoire": False},
            {"nom": "type_carburant", "type": "text", "obligatoire": False},
            {"nom": "consommation_carburant", "type": "number", "obligatoire": False},
            {"nom": "consommation_huile", "type": "number", "obligatoire": False},
            {"nom": "type_propulsion", "type": "text", "obligatoire": False},
        ],
        "description": "Véhicules automobiles (voitures, camions, motos, etc.)"
    },
    {
        "libelle": "Machine de production",
        "code": "MACHINE",
        "compte_comptable": "2441",
        "champs_specifiques": [
            {"nom": "fabricant", "type": "text", "obligatoire": False},
            {"nom": "modele", "type": "text", "obligatoire": False},
            {"nom": "puissance", "type": "number", "obligatoire": False},
            {"nom": "type_alimentation", "type": "text", "obligatoire": False},
            {"nom": "tension_normal", "type": "text", "obligatoire": False},
            {"nom": "service_affecte", "type": "text", "obligatoire": False},
            {"nom": "responsable", "type": "text", "obligatoire": False},
            {"nom": "consommation_elec", "type": "number", "obligatoire": False},
            {"nom": "frequence_maintenance", "type": "text", "obligatoire": False},
            {"nom": "prix_base", "type": "number", "obligatoire": False},
            {"nom": "unites_totales_prevues", "type": "number", "obligatoire": False},
            {"nom": "unites_consommees", "type": "number", "obligatoire": False},
            {"nom": "duree_fournisseur", "type": "number", "obligatoire": False},
        ],
        "description": "Machines et équipements de production"
    },
    {
        "libelle": "Ordinateur",
        "code": "ORDINATEUR",
        "compte_comptable": "2443",
        "champs_specifiques": [
            {"nom": "marque", "type": "text", "obligatoire": False},
            {"nom": "modele", "type": "text", "obligatoire": False},
            {"nom": "processeur", "type": "text", "obligatoire": False},
            {"nom": "ram", "type": "text", "obligatoire": False},
            {"nom": "stockage", "type": "text", "obligatoire": False},
            {"nom": "adresse_ip", "type": "text", "obligatoire": False},
            {"nom": "utilisateur_affecte", "type": "text", "obligatoire": False},
        ],
        "description": "Ordinateurs et équipements informatiques"
    },
    {
        "libelle": "Mobilier",
        "code": "MOBILIER",
        "compte_comptable": "2448",
        "champs_specifiques": [
            {"nom": "materiau", "type": "text", "obligatoire": False},
            {"nom": "couleur", "type": "text", "obligatoire": False},
            {"nom": "dimension", "type": "text", "obligatoire": False},
        ],
        "description": "Mobilier de bureau et équipements"
    },
    {
        "libelle": "Autre",
        "code": "AUTRE",
        "compte_comptable": "2440",
        "champs_specifiques": [],
        "description": "Autres types de biens non classifiés"
    }
]