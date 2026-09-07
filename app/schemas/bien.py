# backend/app/schemas/bien.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Any, Dict
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from ..schemas.cession import CessionResponse


class EtatBienEnum(str, Enum):
    NEUF = "NEUF"
    BON = "BON"
    USAGE = "USAGE"
    PANNE = "PANNE"
    REFORME = "REFORME"
    MAINTENANCE = "MAINTENANCE"
    EN_TEST = "EN_TEST"


class ModePaiementEnum(str, Enum):
    CREDIT = "credit"
    COMPTANT = "comptant"


class ComposantInlineCreate(BaseModel):
    """Composant saisi lors de la création d'une machine de production."""
    numero_serie: str = Field(..., min_length=1, max_length=100)
    prix_achat: Decimal = Field(..., gt=0, description="Prix d'achat du composant (strictement positif)")
    designation: Optional[str] = Field(None, max_length=200)
    duree_vie_ans: int = Field(default=5, ge=1, le=50)


# ============================================================
# SCHEMA DE BASE BIEN AVEC TYPES DYNAMIQUES
# ============================================================

class BienBase(BaseModel):
    """Schéma de base pour un bien avec types dynamiques."""
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = Field(None, gt=0, description="Prix d'acquisition (strictement positif)")
    etat: EtatBienEnum = EtatBienEnum.NEUF
    id_localisation: Optional[int] = Field(None, gt=0, description="ID de la localisation (FK)")
    date_fin_garantie: Optional[date] = None
    description: Optional[str] = None
    image: Optional[str] = None

    # ✅ NOUVEAUX CHAMPS POUR TYPES DYNAMIQUES
    id_type_bien: int = Field(..., gt=0, description="ID du type de bien")
    attributs_specifiques: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Attributs spécifiques au type de bien (JSON)"
    )

    @field_validator("id_localisation", mode="before")
    @classmethod
    def reject_text_localisation(cls, v: Any) -> Any:
        if isinstance(v, str):
            raise ValueError(
                "La localisation doit être transmise sous forme d'identifiant (id_localisation), "
                "pas en texte libre."
            )
        return v

    @field_validator("attributs_specifiques")
    @classmethod
    def validate_attributs(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validation de base des attributs spécifiques."""
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("Les attributs spécifiques doivent être un dictionnaire")
        return v


# ============================================================
# SCHEMA DE CREATION
# ============================================================

class BienCreate(BienBase):
    """Schéma pour la création d'un bien."""
    date_acquisition: date
    mode_paiement: ModePaiementEnum = ModePaiementEnum.CREDIT
    fournisseur_id: Optional[int] = Field(None, gt=0, description="ID du fournisseur (requis si mode_paiement=credit)")
    composants: Optional[List[ComposantInlineCreate]] = None

    @field_validator("fournisseur_id")
    @classmethod
    def validate_fournisseur(cls, v, info):
        mode = info.data.get("mode_paiement")
        if mode == ModePaiementEnum.CREDIT and v is None:
            raise ValueError("Le fournisseur est requis pour un paiement à crédit")
        return v

    @field_validator("id_type_bien")
    @classmethod
    def validate_id_type_bien(cls, v):
        if v <= 0:
            raise ValueError("L'ID du type de bien doit être positif")
        return v

    @model_validator(mode="after")
    def validate_attributs_obligatoires(self):
        """
        Vérifie que tous les champs obligatoires définis dans le type sont présents.
        Cette validation nécessite une vérification en base de données.
        Sera faite dans le service.
        """
        return self


# ============================================================
# SCHEMA DE MISE A JOUR
# ============================================================

class BienUpdate(BaseModel):
    """Schéma pour la mise à jour d'un bien."""
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = Field(None, ge=0)
    etat: Optional[EtatBienEnum] = None
    id_localisation: Optional[int] = Field(None, gt=0)
    date_fin_garantie: Optional[date] = None
    description: Optional[str] = None
    image: Optional[str] = None
    mode_paiement: Optional[ModePaiementEnum] = None
    fournisseur_id: Optional[int] = Field(None, gt=0)
    
    # ✅ NOUVEAUX CHAMPS POUR TYPES DYNAMIQUES
    id_type_bien: Optional[int] = Field(None, gt=0, description="ID du type de bien")
    attributs_specifiques: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Attributs spécifiques au type de bien (JSON)"
    )

    @field_validator("id_localisation", mode="before")
    @classmethod
    def reject_text_localisation(cls, v: Any) -> Any:
        if isinstance(v, str):
            raise ValueError(
                "La localisation doit être transmise sous forme d'identifiant (id_localisation), "
                "pas en texte libre."
            )
        return v

    @field_validator("fournisseur_id")
    @classmethod
    def validate_fournisseur_update(cls, v, info):
        mode = info.data.get("mode_paiement")
        if mode == ModePaiementEnum.CREDIT and v is None:
            raise ValueError("Le fournisseur est requis pour un paiement à crédit")
        return v

    @field_validator("attributs_specifiques")
    @classmethod
    def validate_attributs_update(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("Les attributs spécifiques doivent être un dictionnaire")
        return v

    @model_validator(mode="after")
    def validate_id_type_bien_update(self):
        if self.id_type_bien is not None and self.id_type_bien <= 0:
            raise ValueError("L'ID du type de bien doit être positif")
        return self


# ============================================================
# SCHEMA DE REPONSE
# ============================================================

class LocalisationBrief(BaseModel):
    id_localisation: int
    nom_localisation: str

    class Config:
        from_attributes = True


class TypeBienBrief(BaseModel):
    """Information sommaire sur le type de bien."""
    id: int
    libelle: str
    code: str
    compte_comptable: str

    class Config:
        from_attributes = True


class BienResponse(BienBase):
    """Schéma de réponse pour un bien."""
    id_bien: int
    qr_code: Optional[str] = None
    date_creation: datetime
    statut_comptable: Optional[str] = "ACTIF"
    cumul_amortissement: Optional[Decimal] = Decimal("0")
    cumul_depreciation: Optional[Decimal] = Decimal("0")
    mode_paiement: str
    fournisseur_id: Optional[int] = None
    localisation: Optional[LocalisationBrief] = None
    
    # ✅ NOUVEAU : Informations sur le type de bien
    type_bien_info: Optional[TypeBienBrief] = None
    images: List[Dict[str, str]] = Field(default_factory=list)  # Ajout
    numero_inventaire: str  # Ajout
    
    # ✅ Pour compatibilité ascendante (champs extraits de attributs_specifiques)
    # Ces champs sont dépréciés et seront retirés dans une version future
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
    fabricant: Optional[str] = None
    puissance: Optional[float] = None
    type_alimentation: Optional[str] = None
    tension_normal: Optional[str] = None
    service_affecte: Optional[str] = None
    responsable: Optional[str] = None
    consommation_elec: Optional[float] = None
    frequence_maintenance: Optional[str] = None
    prix_base: Optional[Decimal] = None
    unites_totales_prevues: Optional[int] = None
    unites_consommees: Optional[int] = None
    duree_fournisseur: Optional[int] = None
    processeur: Optional[str] = None
    ram: Optional[str] = None
    stockage: Optional[str] = None
    adresse_ip: Optional[str] = None
    utilisateur_affecte: Optional[str] = None

    class Config:
        from_attributes = True

    def model_post_init(self, __context):
        """Extrait les attributs spécifiques vers les champs dépréciés pour compatibilité."""
        if self.attributs_specifiques:
            for key, value in self.attributs_specifiques.items():
                if hasattr(self, key) and getattr(self, key) is None:
                    setattr(self, key, value)


# ============================================================
# AUTRES SCHEMAS (INCHANGÉS)
# ============================================================

class BienListResponse(BaseModel):
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=500)
    biens: List[BienResponse] = Field(default_factory=list)


class BienCessionInfo(BaseModel):
    """Informations d'un bien pour la cession."""
    id_bien: int
    qr_code: str
    designation: str
    type_bien: str
    date_acquisition: date
    prix_acquisition: Decimal
    valeur_nette_comptable: Optional[Decimal] = None
    etat: EtatBienEnum
    est_amorti: bool
    age_ans: int
    nb_pannes: int
    nb_maintenances: int
    est_eligible_cession: bool
    motifs_ineligibilite: List[str] = Field(default_factory=list)
    
    class Config:
        from_attributes = True


class CessionEligibilityCheck(BaseModel):
    """Schéma pour vérifier l'éligibilité à la cession."""
    id_bien: int
    criteres: dict = Field(
        default_factory=lambda: {
            "nb_pannes_consecutives": 0,
            "seuil_pannes": 3,
            "est_depecie": False,
            "garantie_expiree": True,
            "amortissement_termine": False,
            "cycles_techniques_obligatoires": False
        }
    )
    est_eligible: bool
    motifs: List[str] = Field(default_factory=list)
    recommandation: str

    class Config:
        from_attributes = True


class BienRemplacementResponse(BaseModel):
    """Schéma pour le bien de remplacement."""
    id_bien: int
    qr_code: str
    designation: str
    type_bien: str
    date_acquisition: date
    prix_acquisition: Decimal
    etat: EtatBienEnum
    localisation: Optional[LocalisationBrief] = None
    
    class Config:
        from_attributes = True


class BienAvecCessionResponse(BienResponse):
    """Schéma de réponse d'un bien avec ses informations de cession."""
    est_cede: bool
    cession: Optional[CessionResponse] = None
    actif_remplacement: Optional[BienRemplacementResponse] = None
    est_eligible_cession: bool
    motifs_ineligibilite: List[str] = Field(default_factory=list)
    nb_pannes_consecutives: int
    
    class Config:
        from_attributes = True


class ReferentielOptionsResponse(BaseModel):
    """Schéma pour les options des référentiels."""
    marques_vehicules: List[str] = Field(default_factory=list)
    marques_ordinateurs: List[str] = Field(default_factory=list)
    modeles_vehicules: List[str] = Field(default_factory=list)
    modeles_ordinateurs: List[str] = Field(default_factory=list)
    fabricants_machines: List[str] = Field(default_factory=list)
    processeurs_ordinateurs: List[str] = Field(default_factory=list)
    
    # ✅ NOUVEAU : Types de biens disponibles
    types_biens_disponibles: List[Dict[str, Any]] = Field(default_factory=list)