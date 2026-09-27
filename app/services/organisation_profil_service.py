"""Institutional identity only; no subscription or module changes."""
import io
import logging
import uuid
import warnings
import cloudinary.uploader
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException
from ..models.organisation import Organisation
from ..schemas.organisation_profil import OrganisationProfilResponse
from .audit_service import AuditService

logger = logging.getLogger(__name__)
MAX_LOGO_BYTES = 2 * 1024 * 1024


def document_identity(db, organisation_id):
    org = db.get(Organisation, organisation_id) if organisation_id is not None else None
    return OrganisationProfilResponse.model_validate(org).model_dump() if org else None


class OrganisationProfilService:
    def __init__(self, db):
        self.db = db

    def current(self, user, lock=False):
        if user.organisation_id is None:
            raise HTTPException(403, "Aucune organisation associée à ce compte.")
        query = self.db.query(Organisation).filter(Organisation.id == user.organisation_id)
        if lock:
            query = query.populate_existing().with_for_update()
        org = query.first()
        if org is None:
            raise HTTPException(404, "Organisation introuvable.")
        return org

    def update(self, user, changes, request=None):
        org = self.current(user, lock=True)
        old = {key: getattr(org, key) for key in changes}
        try:
            for key, value in changes.items():
                setattr(org, key, value)
            # Existing audit service commits both the profile and its audit entry.
            AuditService(self.db).log_update(user.id, "organisations", org.id, old, changes, request)
            return org
        except Exception:
            self.db.rollback()
            logger.exception("Échec de mise à jour du profil institutionnel")
            raise HTTPException(500, "Impossible de mettre à jour le profil.")

    @staticmethod
    def validate_logo(content):
        if len(content) > MAX_LOGO_BYTES:
            raise HTTPException(413, "Le logo ne doit pas dépasser 2 Mo.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as img:
                    if img.format not in {"PNG", "JPEG", "WEBP"} or img.width * img.height > 16_000_000:
                        raise ValueError("unsupported image")
                    img.verify()
                with Image.open(io.BytesIO(content)) as img:
                    img.load()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(400, "Format de logo non pris en charge.")

    @staticmethod
    def cleanup(public_id):
        if public_id:
            try:
                cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True, timeout=15)
            except Exception:
                logger.warning("Nettoyage différé nécessaire pour un logo Cloudinary", exc_info=True)

    def upload(self, user, content, request=None):
        self.current(user)
        self.validate_logo(content)
        public_id = f"organisations/{user.organisation_id}/logos/{uuid.uuid4().hex}"
        try:
            result = cloudinary.uploader.upload(io.BytesIO(content), public_id=public_id,
                resource_type="image", overwrite=False, timeout=20)
        except Exception:
            logger.exception("Échec upload logo")
            raise HTTPException(502, "Impossible de mettre à jour le logo. Veuillez réessayer.")
        try:
            org = self.current(user, lock=True)
            old_id = org.logo_public_id
            org = self.update(user, {"logo_url": result["secure_url"], "logo_public_id": result["public_id"]}, request)
        except Exception:
            self.db.rollback()
            self.cleanup(result.get("public_id", public_id))
            raise
        self.cleanup(old_id)
        return org

    def delete_logo(self, user, request=None):
        org = self.current(user, lock=True)
        old_id = org.logo_public_id
        org = self.update(user, {"logo_url": None, "logo_public_id": None}, request)
        self.cleanup(old_id)
        return org
