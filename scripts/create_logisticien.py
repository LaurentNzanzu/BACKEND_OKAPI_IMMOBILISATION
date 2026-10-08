# scripts/create_logisticien.py
# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.core.security import get_password_hash
from sqlalchemy import text


def main():
    db = SessionLocal()
    try:
        # 1. Synchroniser la séquence utilisateurs_id_seq avec le MAX(id)
        db.execute(text("SELECT setval(pg_get_serial_sequence('utilisateurs', 'id'), COALESCE((SELECT MAX(id) FROM utilisateurs), 1));"))
        db.commit()

        # 2. Vérifier le rôle LOGISTICIEN
        role_log = db.query(Role).filter(Role.nom == "LOGISTICIEN").first()
        if not role_log:
            print("[ERREUR] Rôle LOGISTICIEN introuvable en base.", file=sys.stderr)
            return

        # 3. Créer ou mettre à jour le compte logisticien@okapi.cd
        email = "logisticien@okapi.cd"
        user = db.query(Utilisateur).filter(Utilisateur.email == email).first()
        if not user:
            user = Utilisateur(
                organisation_id=2,  # ONG OKAPI
                email=email,
                nom="Logistique",
                prenom="Responsable",
                mot_de_passe=get_password_hash("Logisticien123!"),
                role_id=role_log.id_role,
                est_actif=True,
                doit_changer_mot_de_passe=False,
            )
            db.add(user)
            db.commit()
            print(f"[OK] Compte LOGISTICIEN créé avec succès : ID={user.id}, email={user.email}")
        else:
            user.role_id = role_log.id_role
            user.mot_de_passe = get_password_hash("Logisticien123!")
            user.est_actif = True
            db.commit()
            print(f"[OK] Compte existant mis à jour : ID={user.id}, email={user.email}")

    except Exception as e:
        db.rollback()
        print(f"[ERREUR] Échec de la création : {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
