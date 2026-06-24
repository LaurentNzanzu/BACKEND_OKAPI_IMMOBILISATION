import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from ..models.password_reset_token import PasswordResetToken
from ..models.utilisateur import Utilisateur


class PasswordResetService:
    TOKEN_TTL_HOURS = 1

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_reset_token(self, user_id: int) -> str:
        """Génère un token, stocke son hash en base, retourne le token brut (une seule fois)."""
        self._invalidate_user_tokens(user_id)

        raw_token = secrets.token_urlsafe(32)
        record = PasswordResetToken(
            user_id=user_id,
            token_hash=self._hash_token(raw_token),
            expires_at=datetime.utcnow() + timedelta(hours=self.TOKEN_TTL_HOURS),
        )
        self.db.add(record)
        self.db.commit()
        return raw_token

    def _invalidate_user_tokens(self, user_id: int) -> None:
        now = datetime.utcnow()
        (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .update({"used_at": now}, synchronize_session=False)
        )

    def verify_token(self, raw_token: str) -> bool:
        record = self._get_valid_record(raw_token)
        return record is not None

    def consume_token(self, raw_token: str) -> Optional[Utilisateur]:
        record = self._get_valid_record(raw_token)
        if not record:
            return None

        user = self.db.query(Utilisateur).filter(Utilisateur.id == record.user_id).first()
        if not user:
            return None

        record.used_at = datetime.utcnow()
        self.db.commit()
        return user

    def _get_valid_record(self, raw_token: str) -> Optional[PasswordResetToken]:
        if not raw_token:
            return None
        token_hash = self._hash_token(raw_token)
        record = (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > datetime.utcnow(),
            )
            .first()
        )
        return record
