from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MissionBase(BaseModel):
    projet_id: Optional[int] = None
    type_workflow: Optional[str] = "MISSION"
    statut: Optional[str] = "BROUILLON"
    description: Optional[str] = None
    lieu_depart: Optional[str] = None
    lieu_arrivee: Optional[str] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None
    passagers: Optional[list[Any]] = Field(default_factory=list)
    devise: Optional[str] = "USD"
    observation: Optional[str] = None


class MissionCreate(BaseModel):
    projet_id: Optional[int] = None
    description: str = Field(..., min_length=1, description="Objet ou motif de la mission")
    lieu_depart: str = Field(..., min_length=1, description="Lieu de départ")
    lieu_arrivee: str = Field(..., min_length=1, description="Destination")
    date_debut: datetime = Field(..., description="Date et heure de départ prévues")
    date_fin: datetime = Field(..., description="Date et heure de retour prévues")
    passagers: Optional[list[Any]] = Field(default_factory=list)
    devise: Optional[str] = "USD"
    observation: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Accepte motif comme alias de description
            if "motif" in data and "description" not in data:
                data["description"] = data["motif"]
            # Accepte destination comme alias de lieu_arrivee
            if "destination" in data and "lieu_arrivee" not in data:
                data["lieu_arrivee"] = data["destination"]
            # Accepte date_depart_prevue comme alias de date_debut
            if "date_depart_prevue" in data and "date_debut" not in data:
                data["date_debut"] = data["date_depart_prevue"]
            # Accepte date_retour_prevue comme alias de date_fin
            if "date_retour_prevue" in data and "date_fin" not in data:
                data["date_fin"] = data["date_retour_prevue"]
        return data

    @model_validator(mode="after")
    def validate_dates(self) -> "MissionCreate":
        if self.date_fin <= self.date_debut:
            raise ValueError("La date de fin doit être strictement postérieure à la date de début")
        return self


class MissionUpdate(BaseModel):
    projet_id: Optional[int] = None
    type_workflow: Optional[str] = None
    statut: Optional[str] = None
    description: Optional[str] = None
    lieu_depart: Optional[str] = None
    lieu_arrivee: Optional[str] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None
    passagers: Optional[list[Any]] = None
    devise: Optional[str] = None
    observation: Optional[str] = None
    km_depart: Optional[float] = None
    km_arrivee: Optional[float] = None
    heure_depart_reelle: Optional[datetime] = None
    heure_retour_reelle: Optional[datetime] = None
    photo_depart_url: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self) -> "MissionUpdate":
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            raise ValueError("La date de fin doit être strictement postérieure à la date de début")
        return self


class ChauffeurBrief(BaseModel):
    id: int
    nom: str
    prenom: str
    telephone: Optional[str] = None
    numero_permis: Optional[str] = None
    categorie_permis: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class VehiculeBrief(BaseModel):
    id_bien: int
    immatriculation: Optional[str] = None
    marque: Optional[str] = None
    modele: Optional[str] = None
    categorie: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class MissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organisation_id: int
    numero_mission: Optional[str] = None
    projet_id: Optional[int] = None
    type_workflow: str = "MISSION"
    statut: str
    description: Optional[str] = None
    lieu_depart: Optional[str] = None
    lieu_arrivee: Optional[str] = None
    date_debut: Optional[datetime] = None
    date_fin: Optional[datetime] = None
    passagers: Optional[list[Any]] = Field(default_factory=list)
    km_depart: Optional[float] = None
    km_arrivee: Optional[float] = None
    heure_depart_reelle: Optional[datetime] = None
    heure_retour_reelle: Optional[datetime] = None
    observation: Optional[str] = None
    photo_depart_url: Optional[str] = None
    devise: str = "USD"
    date_creation: datetime
    cree_par: Optional[int] = None
    etape_actuelle_id: Optional[int] = None
    motif_rejet: Optional[str] = None
    valide_par: Optional[int] = None
    date_validation: Optional[datetime] = None

    # Ressources affectées exposées dynamiquement depuis l'affectation active
    chauffeur_id: Optional[int] = None
    vehicule_id: Optional[int] = None
    chauffeur: Optional[ChauffeurBrief] = None
    vehicule: Optional[VehiculeBrief] = None


# Alias pour rétrocompatibilité
MissionRead = MissionResponse


class MissionRejetPayload(BaseModel):
    motif: str = Field(..., min_length=1, description="Motif de rejet obligatoire")


class MissionDemarrerPayload(BaseModel):
    km_depart: float = Field(..., ge=0, description="Kilométrage au compteur au départ")
    heure_depart: Optional[datetime] = Field(None, description="Heure réelle de départ")
    photo_depart_url: Optional[str] = None


class MissionTerminerPayload(BaseModel):
    km_arrivee: float = Field(..., ge=0, description="Kilométrage au compteur à l'arrivée")
    heure_retour: Optional[datetime] = Field(None, description="Heure réelle de retour")
    observation: Optional[str] = None


class MissionAnnulerPayload(BaseModel):
    motif: str = Field(..., min_length=1, description="Motif obligatoire d'annulation")


