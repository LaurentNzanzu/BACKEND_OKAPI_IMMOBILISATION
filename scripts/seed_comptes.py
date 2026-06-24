# backend/scripts/seed_comptes.py
import sys
import os

# Ajouter le chemin du projet pour les imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.plan_comptable import PlanComptable

COMPTES_SYSCOHADA = [
    # Classe 2 - Immobilisations
    {"numero": "244", "libelle": "Immobilisations corporelles", "classe": "2", "type": "actif"},
    {"numero": "2441", "libelle": "Immobilisations corporelles - Machines", "classe": "2", "type": "actif"},
    {"numero": "2443", "libelle": "Immobilisations corporelles - Matériel informatique", "classe": "2", "type": "actif"},
    {"numero": "2445", "libelle": "Immobilisations corporelles - Véhicules", "classe": "2", "type": "actif"},
    {"numero": "2448", "libelle": "Immobilisations corporelles - Mobilier", "classe": "2", "type": "actif"},
    {"numero": "2440", "libelle": "Immobilisations corporelles - Autres", "classe": "2", "type": "actif"},
    {"numero": "2845", "libelle": "Amortissements des immobilisations - Véhicules", "classe": "2", "type": "actif"},
    {"numero": "2843", "libelle": "Amortissements des immobilisations - Matériel informatique", "classe": "2", "type": "actif"},
    {"numero": "2841", "libelle": "Amortissements des immobilisations - Machines", "classe": "2", "type": "actif"},
    {"numero": "2848", "libelle": "Amortissements des immobilisations - Mobilier", "classe": "2", "type": "actif"},
    {"numero": "2840", "libelle": "Amortissements des immobilisations - Autres", "classe": "2", "type": "actif"},
    {"numero": "2944", "libelle": "Dépréciations des immobilisations corporelles", "classe": "2", "type": "actif"},
    
    # Classe 4 - Tiers
    {"numero": "401", "libelle": "Fournisseurs", "classe": "4", "type": "passif"},
    {"numero": "411", "libelle": "Clients", "classe": "4", "type": "actif"},
    {"numero": "481", "libelle": "Fournisseurs d'immobilisations", "classe": "4", "type": "passif"},
    
    # Classe 5 - Trésorerie
    {"numero": "512", "libelle": "Banques", "classe": "5", "type": "actif"},
    
    # Classe 6 - Charges
    {"numero": "681", "libelle": "Dotations aux amortissements d'exploitation", "classe": "6", "type": "charge"},
    {"numero": "6812", "libelle": "Dotations aux amortissements des immobilisations corporelles", "classe": "6", "type": "charge"},
    {"numero": "6914", "libelle": "Dotations aux dépréciations des immobilisations corporelles", "classe": "6", "type": "charge"},
    {"numero": "654", "libelle": "Valeurs comptables des immobilisations cédées - Activité courante", "classe": "6", "type": "charge"},
    
    # Classe 7 - Produits
    {"numero": "754", "libelle": "Produits des cessions d'immobilisations - Activité courante", "classe": "7", "type": "produit"},
    {"numero": "7914", "libelle": "Reprises sur dépréciations des immobilisations corporelles", "classe": "7", "type": "produit"},
    {"numero": "775", "libelle": "Produits des cessions d'immobilisations - Plus-values", "classe": "7", "type": "produit"},
    
    # Classe 8 - Comptes spécifiques
    {"numero": "81", "libelle": "Valeurs comptables des immobilisations cédées - Non courant", "classe": "8", "type": "charge"},
    {"numero": "82", "libelle": "Produits des cessions d'immobilisations - Non courant", "classe": "8", "type": "produit"},
]


def seed_plan_comptable(db: Session):
    """Initialise le plan comptable avec les comptes SYSCOHADA."""
    count = 0
    for compte_data in COMPTES_SYSCOHADA:
        try:
            existing = db.query(PlanComptable).filter(
                PlanComptable.numero == compte_data["numero"]
            ).first()
            if not existing:
                compte = PlanComptable(**compte_data)
                db.add(compte)
                count += 1
                print(f"   ✅ Ajout du compte {compte_data['numero']} - {compte_data['libelle']}")
        except Exception as e:
            print(f"   ⚠️ Erreur sur le compte {compte_data['numero']}: {e}")
    db.commit()
    return count


def get_compte(db: Session, numero: str):
    """Récupère un compte par son numéro."""
    return db.query(PlanComptable).filter(PlanComptable.numero == numero).first()


def get_all_comptes(db: Session, classe: str = None):
    """Récupère tous les comptes, éventuellement filtrés par classe."""
    query = db.query(PlanComptable).filter(PlanComptable.est_actif == True)
    if classe:
        query = query.filter(PlanComptable.classe == classe)
    return query.order_by(PlanComptable.numero).all()


# ============================================================
# POINT D'ENTRÉE POUR L'EXÉCUTION EN LIGNE DE COMMANDE
# ============================================================
if __name__ == "__main__":
    print("🔧 Initialisation du plan comptable SYSCOHADA...")
    
    try:
        db = SessionLocal()
        
        # Vérifier la structure de la table
        print("📋 Vérification de la structure de la table plan_comptable...")
        try:
            # Tester une requête simple
            test = db.query(PlanComptable).first()
            print("   ✅ Table accessible")
        except Exception as e:
            print(f"   ❌ Erreur d'accès à la table: {e}")
            print("   ⚠️ Assurez-vous que la migration a été appliquée: alembic upgrade head")
            db.close()
            sys.exit(1)
        
        # Compter les comptes existants
        existing_count = db.query(PlanComptable).count()
        print(f"📊 Comptes existants avant seed: {existing_count}")
        
        # Exécuter le seed
        count = seed_plan_comptable(db)
        
        # Afficher le résultat
        total = db.query(PlanComptable).count()
        print(f"\n✅ {count} nouveaux comptes insérés.")
        print(f"📊 Total des comptes dans le plan comptable : {total}")
        
        # Afficher les comptes par classe
        print("\n📋 Répartition par classe :")
        classes = db.query(PlanComptable.classe, PlanComptable.type).distinct().all()
        for classe, type_compte in classes:
            nb = db.query(PlanComptable).filter(
                PlanComptable.classe == classe
            ).count()
            print(f"   Classe {classe} ({type_compte}) : {nb} comptes")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)