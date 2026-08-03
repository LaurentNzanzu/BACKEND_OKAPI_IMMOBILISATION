from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
import re

class LoginCredentials(BaseModel):
    """Identifiants de connexion (sans validation de complexité du mot de passe)."""
    email: EmailStr
    mot_de_passe: str


class LoginRequest(BaseModel):
    email: EmailStr
    mot_de_passe: str


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes en secondes


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[datetime] = None
    type: Optional[str] = None
    jti: Optional[str] = None  # ⬅️ Ajout du JTI


class UserAuthResponse(BaseModel):
    id: int
    email: EmailStr
    nom: str
    post_nom: Optional[str] = None
    prenom: str
    telephone: Optional[str] = None
    roles: List[str] = []
    est_actif: bool
    last_login: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    """Réponse de connexion avec Access Token et session UUID."""
    access_token: str
    session_uuid: str  # ⬅️ Nouveau
    user: UserAuthResponse
    expires_in: int = 900  # ⬅️ Nouveau - 15 minutes en secondes


class RefreshTokenResponse(BaseModel):
    """Réponse de rafraîchissement de token."""
    access_token: str
    session_uuid: str  # ⬅️ Nouveau
    expires_in: int = 900  # ⬅️ Nouveau - 15 minutes en secondes


class LogoutResponse(BaseModel):
    message: str = "Déconnexion réussie"


class ChangePasswordRequest(BaseModel):
    ancien_mot_de_passe: str
    nouveau_mot_de_passe: str

    @field_validator('nouveau_mot_de_passe')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères")
        if not re.search(r'[A-Z]', v):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule")
        if not re.search(r'[a-z]', v):
            raise ValueError("Le mot de passe doit contenir au moins une minuscule")
        if not re.search(r'\d', v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    nouveau_mot_de_passe: str

    @field_validator('nouveau_mot_de_passe')
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères")
        if not re.search(r'[A-Z]', v):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule")
        if not re.search(r'[a-z]', v):
            raise ValueError("Le mot de passe doit contenir au moins une minuscule")
        if not re.search(r'\d', v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v


class PasswordResetResponse(BaseModel):
    message: str