from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from urllib.parse import quote_plus

class Settings(BaseSettings):
    """
    Configuration centralisée via variables d'environnement.
    Pydantic lit automatiquement le fichier .env à l'initialisation.
    """
    
    # === Base de données (OBLIGATOIRES) ===
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_PORT: str
    POSTGRES_DB: str
    
    # === Sécurité JWT (OBLIGATOIRES) ===
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_SECRET_KEY: str
    
    # === Redis Configuration ===
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_SESSION_TTL: int = 604800
    REDIS_SOCKET_TIMEOUT: int = 2
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 2
    REDIS_RETRY_ON_TIMEOUT: bool = True
    REDIS_MAX_CONNECTIONS: int = 10
    # 🔴 SUPPRIMEZ LA LIGNE CI-DESSOUS
    # REDIS_URL: Optional[str] = None
    
    # === Configuration SMTP (Optionnel) ===
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    
    # === CORS Configuration ===
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000", 
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    
    # === Application ===
    APP_NAME: str = "Gestion Immobilisations"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    FRONTEND_URL: str = "http://localhost:3000"
    
    # === Session Limits ===
    MAX_ACTIVE_SESSIONS: int = 5
    SESSION_RETENTION_DAYS: int = 30
    REVOKED_SESSION_RETENTION_DAYS: int = 7

    @property
    def DATABASE_URL(self) -> str:
        """
        Construit l'URL de connexion PostgreSQL de manière sécurisée.
        Encode le mot de passe pour gérer les caractères spéciaux.
        """
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        return (
            f"postgresql://{self.POSTGRES_USER}:{encoded_password}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    @property
    def REDIS_URL(self) -> str:
        """Construit l'URL de connexion Redis."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # Configuration Pydantic pour charger le fichier .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

# Instance unique des paramètres (Singleton)
settings = Settings()