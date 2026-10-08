from typing import Optional, Any
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


VALID_STATUTS_CHAUFFEUR = {"DISPONIBLE", "EN_MISSION", "REPOS", "INDISPONIBLE"}


class ChauffeurBase(BaseModel):
    nom: str = Field(..., min_length=1, max_length=100)
    prenom: str = Field(..., min_length=1, max_length=100)
    telephone: Optional[str] = None
    numero_permis: str = Field(..., min_length=1, max_length=100)
    categorie_permis: Optional[str] = None
    type_permis: Optional[str] = None
    date_expiration_permis: Optional[date] = None
    statut: Optional[str] = "DISPONIBLE"
    disponible: Optional[bool] = True
    actif: Optional[bool] = True
    utilisateur_id: Optional[int] = None
    photo_url: Optional[str] = None
    date_embauche: Optional[date] = None
    observations: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def sync_permis_and_status(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normaliser type_permis -> categorie_permis
            if "type_permis" in data and "categorie_permis" not in data:
                data["categorie_permis"] = data["type_permis"]
            elif "categorie_permis" in data and "type_permis" not in data:
                data["type_permis"] = data["categorie_permis"]
            # Synchroniser statut et disponible
            if "statut" in data and data["statut"]:
                stat = str(data["statut"]).upper()
                data["statut"] = stat
                if "disponible" not in data:
                    data["disponible"] = (stat == "DISPONIBLE")
        return data

    @model_validator(mode="after")
    def validate_statut_field(self) -> "ChauffeurBase":
        if self.statut and self.statut.upper() not in VALID_STATUTS_CHAUFFEUR:
            raise ValueError(f"Statut invalide : {self.statut}. Valeurs autorisées : {', '.join(VALID_STATUTS_CHAUFFEUR)}")
        return self


class ChauffeurCreate(ChauffeurBase):
    pass


class ChauffeurUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    telephone: Optional[str] = None
    numero_permis: Optional[str] = None
    categorie_permis: Optional[str] = None
    type_permis: Optional[str] = None
    date_expiration_permis: Optional[date] = None
    statut: Optional[str] = None
    disponible: Optional[bool] = None
    actif: Optional[bool] = None
    utilisateur_id: Optional[int] = None
    photo_url: Optional[str] = None
    date_embauche: Optional[date] = None
    observations: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def sync_permis_and_status(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "type_permis" in data and "categorie_permis" not in data:
                data["categorie_permis"] = data["type_permis"]
            elif "categorie_permis" in data and "type_permis" not in data:
                data["type_permis"] = data["categorie_permis"]
            if "statut" in data and data["statut"]:
                stat = str(data["statut"]).upper()
                data["statut"] = stat
                if "disponible" not in data:
                    data["disponible"] = (stat == "DISPONIBLE")
        return data

    @model_validator(mode="after")
    def validate_statut_update(self) -> "ChauffeurUpdate":
        if self.statut and self.statut.upper() not in VALID_STATUTS_CHAUFFEUR:
            raise ValueError(f"Statut invalide : {self.statut}. Valeurs autorisées : {', '.join(VALID_STATUTS_CHAUFFEUR)}")
        return self


class ChauffeurResponse(ChauffeurBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organisation_id: int
    date_creation: datetime
    utilisateur_id: Optional[int] = None


# Alias rétrocompatible
ChauffeurRead = ChauffeurResponse

