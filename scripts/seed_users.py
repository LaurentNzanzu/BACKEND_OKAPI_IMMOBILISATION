import sys
import os
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
    est_actif: bool = True
) -> bool:
    """
    Crée un utilisateur avec la méthode get_next_id() personnalisée.
    
    Returns:
        bool: True si créé avec succès, False sinon
    """
    db = SessionLocal()
    
    try:
        # 1. Vérifier si l'utilisateur existe déjà
        existing = db.query(Utilisateur).filter(Utilisateur.email == email).first()
        if existing:
            logger.warning(f"Utilisateur '{email}' existe déjà (ID: {existing.id})")
            return False
        
        # 2. Trouver le rôle
        # ⚠️ IMPORTANT : Utiliser id_role (pas id) pour la clé primaire de Role
        role = db.query(Role).filter(Role.nom == role_nom).first()
        if not role:
            logger.error(f"Rôle '{role_nom}' non trouvé en base de données")
            logger.info("💡 Exécutez d'abord: python scripts/seed_roles.py")
            return False
        
        # 3. Calculer le prochain ID avec la méthode personnalisée
        next_id = Utilisateur.get_next_id(db)
        logger.info(f"🔢 Prochain ID disponible pour Utilisateur : {next_id}")
        
        # 4. Hasher le mot de passe
        hashed_password = get_password_hash(mot_de_passe)
        
        # 5. Créer l'utilisateur avec ID manuel
        # ⚠️ IMPORTANT : 
        # - Utilisateur.id (pas id_utilisateur) pour la PK
        # - role.id_role (pas role.id) pour la clé étrangère
        new_user = Utilisateur(
            id=next_id,                        # ← PK de Utilisateur
            email=email,
            nom=nom,
            post_nom=post_nom,
            prenom=prenom,
            telephone=telephone,
            mot_de_passe=hashed_password,      # ← Jamais en clair !
            role_id=role.id_role,              # ← CORRECTION: id_role, PAS id
            est_actif=est_actif
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"✅ Utilisateur créé avec succès !")
        logger.info(f"   ID: {new_user.id}")
        logger.info(f"   Email: {new_user.email}")
        logger.info(f"   Nom: {new_user.nom} {new_user.prenom}")
        logger.info(f"   Rôle: {role_nom}")
        logger.info(f"   Téléphone: {new_user.telephone}")
        logger.info(f"   Actif: {new_user.est_actif}")
        
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur lors de la création : {e}")
        return False
    finally:
        db.close()


def seed_all_users():
    """Crée tous les utilisateurs de test par rôle"""
    logger.info("🚀 Démarrage de l'initialisation des utilisateurs...")
    
    # Liste des utilisateurs à créer
    # ⚠️ Modifications : email admin@it.com, password admin123, téléphone +243
    utilisateurs_test = [
        # ADMIN - ⚠️ IDENTIFIANTS MODIFIÉS
        {
            "email": "laurentnzanzu@gmail.com",              # ← MODIFIÉ
            "mot_de_passe": "Password12",           # ← MODIFIÉ (sans majuscule/! pour simplifier)
            "nom": "Administrateur",
            "prenom": "laurent nkl",
            "role_nom": "ADMIN",
            "telephone": "+243 800 000 001"       # ← MODIFIÉ: +243 (RDC)
        },
        # DG
        {
            "email": "sandramunyaneza@gmail.com",
            "mot_de_passe": "Password1",
            "nom": "Directeur",
            "post_nom": "Général",
            "prenom": "Sandra munyaneza",
            "role_nom": "DG",
            "telephone": "+243 800 000 002"
        },
        # COMPTABLE
        {
            "email": "fatykambasu@gmail.com",
            "mot_de_passe": "Password1",
            "nom": "Comptable",
            "prenom": "Faty kambasu",
            "role_nom": "COMPTABLE",
            "telephone": "+243 800 000 003"
        },
        # TECHNICIEN
        {
            "email": "obedimugisha@gmail.com",
            "mot_de_passe": "Password12",
            "nom": "Technicien",
            "prenom": "Obedi Mugisha",
            "role_nom": "TECHNICIEN",
            "telephone": "+243 800 000 004"
        },
        # CAISSE
        {
            "email": "caisse@gmail.com",
            "mot_de_passe": "caisse123",
            "nom": "Responsable",
            "prenom": "Caisse",
            "role_nom": "CAISSE",
            "telephone": "+243 800 000 005"
        },
         # ✅ NOUVEAU : MAGASINIER
        {
            "email": "christellekambasu@gmail.com",
            "mot_de_passe": "Password1",
            "nom": "Magasinier",
            "prenom": "Christelle Kambasu",
            "role_nom": "MAGASINIER",
            "telephone": "+243 800 000 006"  
        }
    ]
    
    created = 0
    for user_data in utilisateurs_test:
        if create_user(**user_data):
            created += 1
    
    logger.info(f"🎉 Initialisation terminée : {created}/{len(utilisateurs_test)} utilisateurs créés")


if __name__ == "__main__":
    # Mode interactif : créer un seul utilisateur
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        print("=== Création d'un utilisateur (mode interactif) ===\n")
        email = input("Email : ").strip()
        password = input("Mot de passe : ").strip()
        nom = input("Nom : ").strip()
        prenom = input("Prénom : ").strip()
        role = input("Rôle (ADMIN/DG/COMPTABLE/TECHNICIEN/CAISSE) : ").strip().upper()
        post_nom = input("Post-nom (optionnel, Entrée pour passer) : ").strip() or None
        telephone = input("Téléphone (optionnel, Entrée pour passer) : ").strip() or None
        
        success = create_user(
            email=email,
            mot_de_passe=password,
            nom=nom,
            prenom=prenom,
            role_nom=role,
            post_nom=post_nom,
            telephone=telephone
        )
        sys.exit(0 if success else 1)
    
    # Mode batch : créer tous les utilisateurs de test
    else:
        seed_all_users()