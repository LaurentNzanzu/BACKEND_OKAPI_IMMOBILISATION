from typing import Optional
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class OrganisationProfilUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nom: Optional[str] = Field(None, min_length=2, max_length=200)
    sigle: Optional[str] = Field(None, max_length=50)
    forme_juridique: Optional[str] = Field(None, max_length=200)
    rccm: Optional[str] = Field(None, max_length=100)
    id_national: Optional[str] = Field(None, max_length=100)
    numero_impot: Optional[str] = Field(None, max_length=100)
    adresse: Optional[str] = Field(None, max_length=500)
    ville: Optional[str] = Field(None, max_length=100)
    province: Optional[str] = Field(None, max_length=100)
    pays: Optional[str] = Field(None, max_length=100)
    telephone: Optional[str] = Field(None, max_length=100)
    email_contact: Optional[EmailStr] = Field(None, max_length=200)
    site_web: Optional[str] = Field(None, max_length=500)

    @field_validator("*", mode="before")
    @classmethod
    def trim_optional(cls, value, info):
        if isinstance(value, str):
            value = value.strip()
        if info.field_name == "nom" and not value:
            raise ValueError("Le nom de l’organisation est requis.")
        return None if value == "" else value

    @field_validator("site_web")
    @classmethod
    def valid_website(cls, value):
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Le site web doit être une adresse HTTP ou HTTPS valide.")
        return value


class OrganisationProfilResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nom: str
    sigle: Optional[str] = None
    forme_juridique: Optional[str] = None
    rccm: Optional[str] = None
    id_national: Optional[str] = None
    numero_impot: Optional[str] = None
    adresse: Optional[str] = None
    ville: Optional[str] = None
    province: Optional[str] = None
    pays: Optional[str] = None
    telephone: Optional[str] = None
    email_contact: Optional[str] = None
    site_web: Optional[str] = None
    logo_url: Optional[str] = None
