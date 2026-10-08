# backend/scripts/fix_sprint1_permissions_and_tenant.py
# -*- coding: utf-8 -*-
"""
Script idempotent et réversible pour corriger les données du Sprint 1 :
1. Exécute le seed des permissions et rôles de la flotte (seed_permissions_flotte)
2. Active les modules SaaS du plan ENTERPRISE sur l'organisation 2 (ONG OKAPI)
3. Rapproche les utilisateurs de l'ONG (notamment l'administrateur laurentnzanzu@gmail.com)
   à leur organisation (id=2) pour le scoping multi-tenant.

Usage :
    python scripts/fix_sprint1_permissions_and_tenant.py --apply
    python scripts/fix_sprint1_permissions_and_tenant.py --rollback
    python scripts/fix_sprint1_permissions_and_tenant.py --dry-run
"""
import sys
import argparse
import logging
from pathlib import Path

# Ajouter la racine du backend au sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import SessionLocal
from app.models.organisation import Organisation, PlanAbonnement
from app.models.utilisateur import Utilisateur
from app.core.module_registry import get_modules_pour_plan
from scripts.seed_permissions_flotte import main as seed_flotte_main

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TARGET_ORG_ID = 2
USER_EMAILS_TO_LINK = [
    "laurentnzanzu@gmail.com",   # Administrateur de l'ONG
    "sandramunyaneza@gmail.com", # DG
    "fatykambasu@gmail.com",     # Comptable
    "obedimugisha@gmail.com",    # Technicien
    "estherzag@gmail.com",       # Caisse
    "christellekambasu@gmail.com"# Magasinier
]


def apply_fixes(dry_run: bool = False):
    db = SessionLocal()
    try:
        logger.info("=" * 60)
        logger.info(f"APPLY FIXES SPRINT 1 (dry_run={dry_run})")
        logger.info("=" * 60)

        # ÉTAPE 1 : Seed des permissions et rôles de flotte
        logger.info("\n--- 1. SEED DES PERMISSIONS ET RÔLES FLOTTE ---")
        if not dry_run:
            seed_stats = seed_flotte_main()
            logger.info(f"Seed terminé : {seed_stats}")
        else:
            logger.info("[Dry Run] seed_permissions_flotte.main() serait exécuté.")

        # ÉTAPE 2 : Activation des modules sur l'organisation cible
        logger.info(f"\n--- 2. ACTIVATION DES MODULES SUR L'ORGANISATION #{TARGET_ORG_ID} ---")
        org = db.query(Organisation).filter(Organisation.id == TARGET_ORG_ID).first()
        if not org:
            logger.error(f"Organisation #{TARGET_ORG_ID} introuvable en base !")
            return

        plan_name = org.plan_abonnement.value if hasattr(org.plan_abonnement, "value") else str(org.plan_abonnement)
        plan_modules = get_modules_pour_plan(plan_name)
        logger.info(f"Organisation: {org.nom} (Plan: {plan_name})")
        logger.info(f"Modules à activer ({len(plan_modules)}): {plan_modules}")

        current_params = dict(org.parametres_json or {})
        current_modules = set(current_params.get("modules_actifs", []))
        new_modules = sorted(list(current_modules.union(set(plan_modules))))

        current_params["modules_actifs"] = new_modules
        org.parametres_json = current_params
        logger.info(f"Modules actifs mis à jour sur l'organisation #{org.id}.")

        # ÉTAPE 3 : Rattachement des utilisateurs à l'organisation
        logger.info("\n--- 3. RATTACHEMENT DES UTILISATEURS À L'ORGANISATION ---")
        for email in USER_EMAILS_TO_LINK:
            user = db.query(Utilisateur).filter(Utilisateur.email == email).first()
            if not user:
                logger.warning(f"Utilisateur {email} introuvable, ignoré.")
                continue
            if user.organisation_id != TARGET_ORG_ID:
                logger.info(f"Rattachement de {user.email} (ID={user.id}) : org_id {user.organisation_id} -> {TARGET_ORG_ID}")
                user.organisation_id = TARGET_ORG_ID
            else:
                logger.info(f"Utilisateur {user.email} déjà rattaché à l'org #{TARGET_ORG_ID}.")

        if dry_run:
            logger.info("\n[Dry Run] Modifications simulees avec succes, rollback effectue.")
            db.rollback()
        else:
            db.commit()
            logger.info("\n[OK] Toutes les modifications ont ete commitees avec succes en base de donnees.")

    except Exception as e:
        db.rollback()
        logger.error(f"[ERREUR] Erreur lors de l'application des correctifs : {e}", exc_info=True)
        raise
    finally:
        db.close()


def rollback_fixes():
    db = SessionLocal()
    try:
        logger.info("=" * 60)
        logger.info("ROLLBACK FIXES SPRINT 1")
        logger.info("=" * 60)

        # 1. Dé-rattacher les utilisateurs
        logger.info("\n--- 1. DERATTACHEMENT DES UTILISATEURS ---")
        for email in USER_EMAILS_TO_LINK:
            user = db.query(Utilisateur).filter(Utilisateur.email == email).first()
            if user and user.organisation_id == TARGET_ORG_ID:
                logger.info(f"Remise a NULL de organisation_id pour {user.email}")
                user.organisation_id = None

        # 2. Réinitialiser parametres_json de l'organisation
        logger.info(f"\n--- 2. REINITIALISATION DES MODULES DE L'ORGANISATION #{TARGET_ORG_ID} ---")
        org = db.query(Organisation).filter(Organisation.id == TARGET_ORG_ID).first()
        if org and org.parametres_json:
            params = dict(org.parametres_json)
            if "modules_actifs" in params:
                del params["modules_actifs"]
            org.parametres_json = params if params else None
            logger.info("parametres_json reinitialise.")

        db.commit()
        logger.info("\n[OK] Rollback effectue avec succes.")
    except Exception as e:
        db.rollback()
        logger.error(f"[ERREUR] Erreur lors du rollback : {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix sprint 1 permissions and tenant association")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Appliquer les corrections")
    group.add_argument("--rollback", action="store_true", help="Annuler les corrections (revert)")
    group.add_argument("--dry-run", action="store_true", help="Simuler l'application sans committer")

    args = parser.parse_args()
    if args.apply:
        apply_fixes(dry_run=False)
    elif args.rollback:
        rollback_fixes()
    elif args.dry_run:
        apply_fixes(dry_run=True)
