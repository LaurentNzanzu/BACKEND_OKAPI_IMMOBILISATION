# backend/scripts/fix_database.py
"""
Script pour corriger les incohérences de la base de données
Exécuter : python -m backend.scripts.fix_database
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine
from app.models import Role, Permission, Utilisateur
from sqlalchemy import text

def fix_database():
    print("🔧 Correction de la base de données...")
    db = SessionLocal()
    
    try:
        # 1. Vérifier les rôles existants
        roles = db.query(Role).all()
        print(f"📋 Rôles trouvés : {[r.nom for r in roles]}")
        
        # 2. Vérifier l'utilisateur ADMIN
        admin = db.query(Utilisateur).filter(Utilisateur.email == "admin@it.com").first()
        if admin:
            print(f"✅ Admin trouvé : {admin.email}")
            print(f"   Rôle ID: {admin.role_id}")
            if admin.role:
                print(f"   Rôle nom: {admin.role.nom}")
            else:
                print(f"❌ ERREUR: L'admin n'a pas de rôle associé !")
                
                # Corriger : Assigner le rôle ADMIN
                admin_role = db.query(Role).filter(Role.nom == "ADMIN").first()
                if admin_role:
                    admin.role_id = admin_role.id_role
                    db.commit()
                    print(f"✅ Rôle ADMIN assigné à l'utilisateur {admin.email}")
                else:
                    print(f"❌ Rôle ADMIN non trouvé dans la base !")
        else:
            print(f"❌ Admin non trouvé !")
        
        # 3. Vérifier les permissions
        permissions = db.query(Permission).all()
        print(f"📋 Permissions trouvées : {len(permissions)}")
        
        # 4. Exécuter une requête SQL pour vérifier les relations
        result = db.execute(text("""
            SELECT r.nom as role_nom, COUNT(u.id) as user_count
            FROM roles r
            LEFT JOIN utilisateurs u ON u.role_id = r.id_role
            GROUP BY r.id_role, r.nom
        """))
        
        print("\n📊 Récapitulatif des rôles et utilisateurs :")
        for row in result:
            print(f"   - {row.role_nom}: {row.user_count} utilisateur(s)")
        
        print("\n✅ Correction terminée !")
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        db.rollback()
    finally:
        db.close()

def recreate_permissions():
    """Recréer les permissions de base si nécessaire"""
    db = SessionLocal()
    
    try:
        # Permissions de base pour ADMIN
        base_permissions = [
            {"nom": "users:manage", "module": "utilisateurs", "action": "manage"},
            {"nom": "users:create", "module": "utilisateurs", "action": "create"},
            {"nom": "users:read", "module": "utilisateurs", "action": "read"},
            {"nom": "users:update", "module": "utilisateurs", "action": "update"},
            {"nom": "users:delete", "module": "utilisateurs", "action": "delete"},
            {"nom": "biens:manage", "module": "biens", "action": "manage"},
            {"nom": "biens:create", "module": "biens", "action": "create"},
            {"nom": "biens:read", "module": "biens", "action": "read"},
            {"nom": "biens:update", "module": "biens", "action": "update"},
            {"nom": "biens:delete", "module": "biens", "action": "delete"},
            {"nom": "dashboard:view", "module": "dashboard", "action": "view"},
            {"nom": "reports:view", "module": "rapports", "action": "view"},
            {"nom": "audit:view", "module": "audit", "action": "view"},
        ]
        
        for perm_data in base_permissions:
            existing = db.query(Permission).filter(Permission.nom == perm_data["nom"]).first()
            if not existing:
                new_perm = Permission(
                    nom=perm_data["nom"],
                    module=perm_data["module"],
                    action=perm_data["action"],
                    actif=True
                )
                db.add(new_perm)
                print(f"✅ Permission ajoutée : {perm_data['nom']}")
        
        db.commit()
        
        # Assigner toutes les permissions au rôle ADMIN
        admin_role = db.query(Role).filter(Role.nom == "ADMIN").first()
        if admin_role:
            all_perms = db.query(Permission).all()
            admin_role.permissions = all_perms
            db.commit()
            print(f"✅ Toutes les permissions assignées au rôle ADMIN")
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 50)
    print("🔧 SCRIPT DE CORRECTION DE LA BASE DE DONNÉES")
    print("=" * 50)
    
    fix_database()
    recreate_permissions()
    
    print("\n✨ Correction terminée ! Redémarrez votre application.")