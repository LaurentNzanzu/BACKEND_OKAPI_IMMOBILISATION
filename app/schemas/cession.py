# app/schemas/cession.py (extrait modifié)
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Optional, List
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class TypeCessionEnum(str, Enum):
    """Type de cession"""
    COURANTE = "courante"
    NON_COURANTE = "non_courante"
    MISE_AU_REBUT = "mise_au_rebut"


class StatutCessionEnum(str, Enum):
    """Statut d'une cession"""
    ELIGIBLE = "ELIGIBLE"
    EN_ATTENTE_VALIDATION = "EN_ATTENTE_VALIDATION"
    EN_COURS = "EN_COURS"
    ACCORDEE = "ACCORDEE"
    REJETEE = "REJETEE"
    TERMINEE = "TERMINEE"


class ModeReglementEnum(str, Enum):
    """Mode de règlement"""
    COMPTANT = "comptant"
    CREDIT = "credit"
    VIREMENT = "virement"
    CHEQUE = "cheque"
    ESPECE = "espece"


class CessionCreate(BaseModel):
    """Schéma pour la création d'une cession."""
    id_bien: int = Field(..., gt=0, description="ID du bien à céder")
    date_cession: date = Field(..., description="Date de la cession")
    prix_vente: Optional[Decimal] = Field(None, gt=0, description="Prix de vente")
    prix_cession: Optional[Decimal] = Field(None, gt=0, description="Prix de cession (alias)")
    valeur_nette_comptable: Optional[Decimal] = Field(None, ge=0, description="VNC au moment de la cession")
    acheteur: Optional[str] = Field(None, max_length=200, description="Nom de l'acheteur")
    mode_reglement: Optional[ModeReglementEnum] = None
    type_cession: TypeCessionEnum = TypeCessionEnum.COURANTE
    motif: Optional[str] = Field(None, min_length=5, max_length=500, description="Motif de la cession")
    
    # === NOUVEAUX CHAMPS TÂCHE 2 ===
    actif_remplacement_id: Optional[int] = Field(None, gt=0, description="ID du nouveau bien acquis en remplacement")
    piece_justificative_url: Optional[str] = Field(None, max_length=500)
    commentaire: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def resolve_prix(self):
        """Résout le prix entre prix_vente et prix_cession."""
        if self.prix_vente is None and self.prix_cession is not None:
            object.__setattr__(self, "prix_vente", self.prix_cession)
        if self.prix_vente is None:
            raise ValueError("prix_vente ou prix_cession est requis")
        return self

    @model_validator(mode="after")
    def validate_actif_remplacement(self):
        """Vérifie que le bien de remplacement n'est pas le même que le bien cédé."""
        if self.actif_remplacement_id is not None and self.actif_remplacement_id == self.id_bien:
            raise ValueError("Le bien de remplacement ne peut pas être le même que le bien cédé")
        return self

    @model_validator(mode="after")
    def validate_date_cession(self):
        """Vérifie que la date de cession n'est pas dans le futur."""
        if self.date_cession > date.today():
            raise ValueError("La date de cession ne peut être dans le futur")
        return self


class CessionUpdate(BaseModel):
    """Schéma pour la mise à jour d'une cession."""
    date_cession: Optional[date] = None
    prix_vente: Optional[Decimal] = Field(None, gt=0)
    acheteur: Optional[str] = Field(None, max_length=200)
    mode_reglement: Optional[ModeReglementEnum] = None
    type_cession: Optional[TypeCessionEnum] = None
    motif: Optional[str] = Field(None, min_length=5, max_length=500)
    actif_remplacement_id: Optional[int] = Field(None, gt=0)
    piece_justificative_url: Optional[str] = Field(None, max_length=500)
    commentaire: Optional[str] = Field(None, max_length=500)
    statut: Optional[StatutCessionEnum] = None

    @model_validator(mode="after")
    def validate_date_cession_update(self):
        if self.date_cession and self.date_cession > date.today():
            raise ValueError("La date de cession ne peut être dans le futur")
        return self


class RebutCreate(BaseModel):
    """Schéma pour la mise au rebut d'un bien."""
    id_bien: int = Field(..., gt=0, description="ID du bien à mettre au rebut")
    date_rebut: Optional[date] = Field(None, description="Date de mise au rebut")
    motif: str = Field(..., min_length=3, max_length=500, description="Motif de la mise au rebut")
    piece_justificative_url: Optional[str] = Field(None, max_length=500)
    commentaire: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_date_rebut(self):
        if self.date_rebut and self.date_rebut > date.today():
            raise ValueError("La date de mise au rebut ne peut être dans le futur")
        return self


# ============================================================
# RESTE DU FICHIER INCHANGÉ
# ============================================================

class CessionEligibilityResponse(BaseModel):
    """Schéma pour vérifier l'éligibilité d'un bien à la cession."""
    id_bien: int
    qr_code: str
    designation: str
    est_eligible: bool
    statut_cession: StatutCessionEnum
    criteres: dict = Field(..., description="Détail des critères d'éligibilité")
    motifs_ineligibilite: List[str] = Field(default_factory=list)
    nombre_pannes_consecutives: int
    est_depecie: bool
    garantie_expiree: bool
    amortissement_termine: bool
    cycles_techniques_obligatoires: bool
    recommandation: str
    nb_pannes_totales: int
    nb_maintenances: int
    age_bien_ans: int
    valeur_nette_comptable: Optional[Decimal] = None

    class Config:
        from_attributes = True


class CessionResponse(BaseModel):
    """Schéma de réponse pour une cession."""
    id_cession: int
    id_bien: int
    qr_code_bien: Optional[str] = None
    designation_bien: Optional[str] = None
    date_cession: date
    prix_vente: Decimal
    valeur_nette_comptable: Optional[Decimal] = None
    resultat: Optional[Decimal] = Field(None, description="Résultat de cession (PV - VNC)")
    acheteur: Optional[str] = None
    mode_reglement: Optional[str] = None
    type_cession: str
    motif: Optional[str] = None
    statut: StatutCessionEnum
    actif_remplacement_id: Optional[int] = None
    actif_remplacement_qr_code: Optional[str] = None
    actif_remplacement_designation: Optional[str] = None
    piece_justificative_url: Optional[str] = None
    commentaire: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    cree_par: Optional[int] = None
    cree_par_nom: Optional[str] = None
    validations: List[dict] = Field(default_factory=list)
    statut_validation: str = "EN_ATTENTE"
    ecritures: List[dict] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CessionValidationWorkflow(BaseModel):
    """Schéma pour le workflow de validation d'une cession."""
    id_bien: int
    id_cession: int
    etape_actuelle: str
    prochaine_etape: Optional[str] = None
    validation_comptable: Optional[dict] = None
    validation_caissier: Optional[dict] = None
    validation_dg: Optional[dict] = None
    est_complete: bool
    est_approuvee: bool
    statut_global: StatutCessionEnum
    date_demande: datetime
    date_validation_comptable: Optional[datetime] = None
    date_validation_caissier: Optional[datetime] = None
    date_validation_dg: Optional[datetime] = None
    date_cession_effective: Optional[date] = None


class CessionListResponse(BaseModel):
    """Schéma pour la liste des cessions."""
    total: int
    page: int
    page_size: int
    cessions: List[CessionResponse]
    filtres: Optional[dict] = None


class CessionStatistiques(BaseModel):
    """Schéma pour les statistiques des cessions."""
    total_cessions: int
    total_cessions_validees: int
    total_cessions_rejetees: int
    total_montant_cessions: Decimal
    total_montant_cessions_par_type: dict
    cessions_par_mois: List[dict]
    cessions_par_type: dict
    cessions_par_statut: dict
    resultat_moyen_cession: Optional[Decimal] = None
    bien_plus_ceder: Optional[dict] = None
    cessions_remplacement: int