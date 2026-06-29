# backend/app/schemas/bien.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Any
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


class ModePaiementEnum(str, Enum):
    CREDIT = "credit"
    COMPTANT = "comptant"


class ComposantInlineCreate(BaseModel):
    """Composant saisi lors de la création d'une machine de production."""
    numero_serie: str = Field(..., min_length=1, max_length=100)
    prix_achat: Decimal = Field(..., gt=0, description="Prix d'achat du composant (strictement positif)")
    designation: Optional[str] = Field(None, max_length=200)
    duree_vie_ans: int = Field(default=5, ge=1, le=50)


class BienBase(BaseModel):
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = Field(None, gt=0, description="Prix d'acquisition (strictement positif)")
    etat: EtatBienEnum = EtatBienEnum.NEUF
    id_localisation: int = Field(..., gt=0, description="ID de la localisation (FK)")
    date_fin_garantie: Optional[date] = None
    description: Optional[str] = None
    image: Optional[str] = None

    @field_validator("id_localisation", mode="before")
    @classmethod
    def reject_text_localisation(cls, v: Any) -> Any:
        if isinstance(v, str):
            raise ValueError(
                "La localisation doit être transmise sous forme d'identifiant (id_localisation), "
                "pas en texte libre."
            )
        return v


class BienCreate(BienBase):
    type_bien: str = Field(..., min_length=1, description="Type de bien (vehicule, machine, ordinateur)")
    date_acquisition: date

    mode_paiement: ModePaiementEnum = ModePaiementEnum.CREDIT
    fournisseur_id: Optional[int] = Field(None, gt=0, description="ID du fournisseur (requis si mode_paiement=credit)")

    @field_validator("fournisseur_id")
    @classmethod
    def validate_fournisseur(cls, v, info):
        mode = info.data.get("mode_paiement")
        if mode == ModePaiementEnum.CREDIT and v is None:
            raise ValueError("Le fournisseur est requis pour un paiement à crédit")
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

    # Champs spécifiques machines de production
    prix_base: Optional[Decimal] = Field(None, gt=0)
    fabricant: Optional[str] = None
    puissance: Optional[float] = None
    type_alimentation: Optional[str] = None
    tension_normal: Optional[str] = None
    service_affecte: Optional[str] = None
    responsable: Optional[str] = None
    consommation_elec: Optional[float] = None
    frequence_maintenance: Optional[str] = None
    unites_totales_prevues: Optional[int] = Field(None, gt=0)
    unites_consommees: Optional[int] = Field(None, ge=0)
    duree_fournisseur: Optional[int] = Field(None, gt=0)
    composants: Optional[List[ComposantInlineCreate]] = None

    # Champs spécifiques ordinateurs
    processeur: Optional[str] = None
    ram: Optional[str] = None
    stockage: Optional[str] = None
    adresse_ip: Optional[str] = None
    utilisateur_affecte: Optional[str] = None

    @model_validator(mode="after")
    def validate_machine_pricing(self):
        if self.type_bien != "machine":
            return self

        prix_base = self.prix_base or Decimal("0")
        composants = self.composants or []
        total_composants = sum((c.prix_achat for c in composants), Decimal("0"))
        prix_calcule = prix_base + total_composants

        if self.prix_acquisition is not None and self.prix_acquisition != prix_calcule:
            raise ValueError(
                "Le prix d'acquisition d'une machine de production est calculé automatiquement "
                "(prix de base + somme des prix d'achat des composants). "
                "Ne soumettez pas de valeur manuelle."
            )

        object.__setattr__(self, "prix_acquisition", prix_calcule)
        return self


class BienUpdate(BaseModel):
    date_acquisition: Optional[date] = None
    prix_acquisition: Optional[Decimal] = Field(None, ge=0)  # ✅ ge=0 pour update (permet annulation)
    etat: Optional[EtatBienEnum] = None
    id_localisation: Optional[int] = Field(None, gt=0)
    date_fin_garantie: Optional[date] = None
    description: Optional[str] = None
    image: Optional[str] = None

    mode_paiement: Optional[ModePaiementEnum] = None
    fournisseur_id: Optional[int] = Field(None, gt=0)

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

    prix_base: Optional[Decimal] = Field(None, ge=0)
    fabricant: Optional[str] = None
    puissance: Optional[float] = None
    type_alimentation: Optional[str] = None
    tension_normal: Optional[str] = None
    service_affecte: Optional[str] = None
    responsable: Optional[str] = None
    consommation_elec: Optional[float] = None
    frequence_maintenance: Optional[str] = None
    unites_totales_prevues: Optional[int] = None
    unites_consommees: Optional[int] = None
    duree_fournisseur: Optional[int] = None

    processeur: Optional[str] = None
    ram: Optional[str] = None
    stockage: Optional[str] = None
    adresse_ip: Optional[str] = None
    utilisateur_affecte: Optional[str] = None

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


class LocalisationBrief(BaseModel):
    id_localisation: int
    nom_localisation: str

    class Config:
        from_attributes = True


class BienResponse(BienBase):
    id_bien: int
    qr_code: str
    date_creation: datetime
    type_bien: str
    statut_comptable: Optional[str] = "ACTIF"
    cumul_amortissement: Optional[Decimal] = Decimal("0")
    cumul_depreciation: Optional[Decimal] = Decimal("0")
    mode_paiement: str
    fournisseur_id: Optional[int] = None
    localisation: Optional[LocalisationBrief] = None

    type_vehicule: Optional[str] = None
    immatriculation: Optional[str] = None
    fabricant: Optional[str] = None
    processeur: Optional[str] = None
    prix_base: Optional[Decimal] = None
    unites_totales_prevues: Optional[int] = None
    unites_consommees: Optional[int] = None
    duree_fournisseur: Optional[int] = None

    class Config:
        from_attributes = True


# ============================================================
# SCHÉMAS DE PAGINATION MIS À JOUR
# ============================================================

class BienListResponse(BaseModel):
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=500)
    biens: List[BienResponse] = Field(default_factory=list)


# ============================================================
# SCHÉMAS POUR LA CESSION (TÂCHE 2)
# ============================================================

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