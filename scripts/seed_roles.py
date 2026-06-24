# -*- coding: utf-8 -*-
"""
Script d'initialisation des rôles de base dans la base de données.
Utilise la méthode get_next_id() pour la gestion manuelle des IDs.
"""
import sys
import os
from pathlib import Path

# Ajouter le dossier backend au PATH pour les imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.core.database import SessionLocal
from app.models.role import Role
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def seed_roles():
    """
    Insère les rôles par défaut dans la base de données.
    Utilise Role.get_next_id() pour calculer les IDs manuellement.
    """
    db = SessionLocal()
    
    # Rôles par défaut du système RBAC (noms en MAJUSCULES comme dans enums.py)
    roles_defaut = [
        {"nom": "ADMIN", "description": "Administrateur système - Accès complet à toutes les fonctionnalités"},
        {"nom": "DG", "description": "Directeur Général - Vision stratégique et validation des décisions"},
        {"nom": "COMPTABLE", "description": "Comptable - Gestion financière, amortissements et validations budgétaires"},
        {"nom": "TECHNICIEN", "description": "Technicien - Déclaration de pannes, interventions et maintenance"},
        {"nom": "CAISSE", "description": "Responsable caisse - Validation finale des dépenses et paiements"},
        {"nom": "MAGASINIER", "description": "Magasinier - Gestion des pièces détachées, du stock et des commandes"}
    ]
    
    logger.info("🔄 Démarrage de l'initialisation des rôles...")
    
    for role_data in roles_defaut:
        nom_role = role_data["nom"]
        
        # Vérifier si le rôle existe déjà
        existing_role = db.query(Role).filter(Role.nom == nom_role).first()
        
        if existing_role:
            logger.info(f"⏭️  Rôle '{nom_role}' déjà existant (ID: {existing_role.id_role})")
            continue
        
        # Calculer le prochain ID avec la méthode personnalisée
        next_id = Role.get_next_id(db)
        logger.info(f"➕ Création du rôle '{nom_role}' avec ID personnalisé : {next_id}")
        
        # ⚠️ IMPORTANT : Utiliser 'id_role' (pas 'id') car c'est le nom de la PK dans le modèle Role
        new_role = Role(
            id_role=next_id,                    # ← CORRECTION : id_role, PAS id
            nom=nom_role,
            description=role_data["description"],
            actif=True
        )
        
        try:
            db.add(new_role)
            db.commit()
            db.refresh(new_role)
            logger.info(f"✅ Rôle '{nom_role}' créé avec succès (ID: {new_role.id_role})")
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Erreur lors de la création du rôle '{nom_role}': {e}")
            raise
    
    db.close()
    logger.info("🎉 Initialisation des rôles terminée avec succès !")


if __name__ == "__main__":
    try:
        seed_roles()
    except KeyboardInterrupt:
        logger.warning("⚠️  Processus interrompu par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Erreur fatale : {e}")
        sys.exit(1)