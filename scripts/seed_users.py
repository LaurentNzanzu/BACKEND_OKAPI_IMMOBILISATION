import sys
from pathlib import Path

# Ajouter le dossier backend au PATH pour les imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.core.database import SessionLocal
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.core.security import get_password_hash
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def create_user(
    email: str,
    mot_de_passe: str,
    nom: str,
    prenom: str,
    role_nom: str,
    post_nom: str = None,
    telephone: str = None,
    est_actif: bool = True,
    organisation_id: int = None,      # ✅ NOUVEAU : multi-tenant
) -> bool:
    """
    Crée un utilisateur.
    - organisation_id = None  → ADMIN plateforme
    - organisation_id = <int> → utilisateur rattaché à une ONG
    """
    db = SessionLocal()

    try:
        # 1. Vérifier si l'utilisateur existe déjà
        existing = db.query(Utilisateur).filter(Utilisateur.email == email).first()
        if existing:
            logger.warning(f"Utilisateur '{email}' existe déjà (ID: {existing.id})")
            return False

        # 2. Trouver le rôle
        role = db.query(Role).filter(Role.nom == role_nom).first()
        if not role:
            logger.error(f"Rôle '{role_nom}' non trouvé en base de données")
            logger.info("💡 Exécutez d'abord: python scripts/seed_permissions.py")
            return False

        # 3. Calculer le prochain ID
        next_id = Utilisateur.get_next_id(db)
        logger.info(f"🔢 Prochain ID disponible pour Utilisateur : {next_id}")

        # 4. Hasher le mot de passe
        hashed_password = get_password_hash(mot_de_passe)

        # 5. Créer l'utilisateur
        new_user = Utilisateur(
            id=next_id,
            email=email,
            nom=nom,
            post_nom=post_nom,
            prenom=prenom,
            telephone=telephone,
            mot_de_passe=hashed_password,
            role_id=role.id_role,
            est_actif=est_actif,
            organisation_id=organisation_id,   # ✅ NULL = ADMIN plateforme
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info("✅ Utilisateur créé avec succès !")
        logger.info(f"   ID: {new_user.id}")
        logger.info(f"   Email: {new_user.email}")
        logger.info(f"   Nom: {new_user.nom} {new_user.prenom}")
        logger.info(f"   Rôle: {role_nom}")
        logger.info(f"   Organisation: {new_user.organisation_id} "
                    f"({'PLATEFORME' if new_user.organisation_id is None else 'ONG'})")
        logger.info(f"   is_platform_admin: {new_user.is_platform_admin}")
        logger.info(f"   is_org_admin: {new_user.is_org_admin}")
        logger.info(f"   Téléphone: {new_user.telephone}")
        logger.info(f"   Actif: {new_user.est_actif}")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur lors de la création : {e}")
        return False
    finally:
        db.close()


def seed_platform_admin():
    """
    Crée UNIQUEMENT l'ADMIN plateforme (organisation_id = NULL).
    """
    logger.info("🚀 Création de l'ADMIN plateforme...")

    admin_platform = {
        "email": "laurentnzanzu@gmail.com",
        "mot_de_passe": "Password12",
        "nom": "Administrateur",
        "prenom": "laurent nkl",
        "role_nom": "ADMIN",
        "telephone": "+243800000001",     # ⚠️ sans espace (validation Pydantic)
        "organisation_id": None,          # ✅ ADMIN PLATEFORME
    }

    success = create_user(**admin_platform)

    if success:
        logger.info("🎉 ADMIN plateforme créé avec succès")
    else:
        logger.warning("⚠️ Aucun utilisateur créé (déjà existant ou erreur)")


if __name__ == "__main__":
    seed_platform_admin()