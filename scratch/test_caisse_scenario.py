# scratch/test_caisse_scenario.py
import sys
import os
from datetime import datetime

# Ajouter le dossier parent au chemin
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.caisse import Caisse
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.models.bien import Bien
from app.models.besoin import Besoin, StatutBesoin
from app.models.validation import Validation, OrdreValidation, DecisionValidation, TypeValidation
from app.models.amortissement import Amortissement, StatutAmortissement
from app.models.ecriture_comptable import EcritureComptable, StatutEcriture
from app.services.caisse_service import CaisseService
from app.services.mouvement_caisse_service import MouvementCaisseService
from app.services.validation_service import ValidationService
from app.services.amortissement_workflow_service import AmortissementWorkflowService


def test_scenario():
    db = SessionLocal()
    print("=== DÉBUT DU SCÉNARIO DE TEST DE LA CAISSE ===")

    try:
        # 1. Vérification des utilisateurs de test ou création
        print("\n--- 1. Récupération des utilisateurs pour les rôles ---")
        comptable = db.query(Utilisateur).join(Role).filter(Role.nom == "COMPTABLE").first()
        caissier = db.query(Utilisateur).join(Role).filter(Role.nom == "CAISSE").first()
        dg = db.query(Utilisateur).join(Role).filter(Role.nom == "DG").first()

        if not comptable or not caissier or not dg:
            # Récupérer les rôles
            role_comp = db.query(Role).filter(Role.nom == "COMPTABLE").first()
            role_caisse = db.query(Role).filter(Role.nom == "CAISSE").first()
            role_dg = db.query(Role).filter(Role.nom == "DG").first()
            
            # Créer des utilisateurs si absents
            if not comptable and role_comp:
                comptable = Utilisateur(nom_complet="Test Comptable", email="comp@test.com", password_hash="hash", id_role=role_comp.id_role, est_actif=True)
                db.add(comptable)
            if not caissier and role_caisse:
                caissier = Utilisateur(nom_complet="Test Caissier", email="caisse@test.com", password_hash="hash", id_role=role_caisse.id_role, est_actif=True)
                db.add(caissier)
            if not dg and role_dg:
                dg = Utilisateur(nom_complet="Test DG", email="dg@test.com", password_hash="hash", id_role=role_dg.id_role, est_actif=True)
                db.add(dg)
            db.commit()
            db.refresh(comptable)
            db.refresh(caissier)
            db.refresh(dg)

        print(f"Comptable : {comptable.nom_complet} (ID: {comptable.id})")
        print(f"Caissier : {caissier.nom_complet} (ID: {caissier.id})")
        print(f"DG : {dg.nom_complet} (ID: {dg.id})")

        # 2. Récupération ou création de la Caisse principale
        print("\n--- 2. Initialisation de la caisse ---")
        caisse_service = CaisseService(db)
        mouvement_service = MouvementCaisseService(db)
        
        caisse = db.query(Caisse).filter(Caisse.statut == "ACTIF").first()
        if not caisse:
            caisse = Caisse(solde_physique=0.0, solde_theorique=0.0, devise="USD", statut="ACTIF")
            db.add(caisse)
            db.commit()
            db.refresh(caisse)
        
        solde_initial = caisse.solde_physique
        print(f"Caisse Principale (ID: {caisse.id_caisse}) - Solde initial : {solde_initial} USD")

        # 3. Entrée de fonds / Approvisionnement (Rapprochement bancaire, BEC)
        print("\n--- 3. Test de l'entrée de fonds (Approvisionnement) ---")
        montant_entree = 10000.0
        # Simulation d'approvisionnement via mouvement_service
        from app.schemas.mouvement_caisse import MouvementCaisseCreate
        mvt_create = MouvementCaisseCreate(
            id_caisse=caisse.id_caisse,
            type_mouvement="ENTREE",
            montant=montant_entree,
            motif="Approvisionnement initial de la caisse",
            origine_type="BANQUE",
            origine_id=1,
            mode_reglement="VIREMENT",
            beneficiaire="Caisse Centrale"
        )
        
        mvt = mouvement_service.creer_mouvement(mvt_create)
        print(f"Mouvement d'entrée créé : {mvt.numero_piece} (Montant: {mvt.montant} USD, Statut: {mvt.statut})")
        
        # Validation du mouvement d'entrée par le caissier
        mvt_valide = mouvement_service.valider_mouvement(mvt.id_mouvement, caissier.id)
        db.refresh(caisse)
        print(f"Mouvement validé par le Caissier. Nouveau solde caisse : {caisse.solde_physique} USD")
        assert caisse.solde_physique == solde_initial + montant_entree, "Le solde physique n'a pas été incrémenté correctement !"
        print("[OK] Test d'approvisionnement reussi.")

        # 4. Test d'une validation d'acquisition/besoin (Sortie de caisse après validation DG)
        print("\n--- 4. Test de validation d'un besoin (Sortie Caisse) ---")
        # Récupération ou création d'une Panne de test
        from app.models.panne import Panne
        panne = db.query(Panne).first()
        if not panne:
            bien_temp = db.query(Bien).first()
            if not bien_temp:
                bien_temp = Bien(
                    nom_bien="Ordinateur portable de test",
                    categorie="INFORMATIQUE",
                    valeur_origine=2000.0,
                    prix_acquisition=2000.0,
                    date_acquisition=datetime.utcnow(),
                    date_mise_en_service=datetime.utcnow(),
                    statut_comptable="ACTIF"
                )
                db.add(bien_temp)
                db.flush()
            panne = Panne(
                id_bien=bien_temp.id_bien,
                description="Panne de test pour besoin",
                date_panne=datetime.utcnow(),
                statut="OUVERT",
                priorite="HAUTE"
            )
            db.add(panne)
            db.flush()

        # Création d'un besoin de test
        import time
        demand_num = f"BESOIN-TEST-{int(time.time())}"
        besoin = Besoin(
            numero_demande=demand_num,
            montant_total=1500.00,
            statut=StatutBesoin.EN_VALIDATION,
            id_panne=panne.id_panne
        )
        db.add(besoin)
        db.flush()

        # DG valide le besoin
        val_service = ValidationService(db)
        print(f"DG valide le besoin {besoin.numero_demande} pour 1500.00 USD...")
        
        # Simuler le processus d'approbation DG dans le service
        validation = Validation(
            type_validation=TypeValidation.BESOIN,
            id_besoin=besoin.id_besoin,
            ordre_validateur=OrdreValidation.DG,
            id_validateur=dg.id,
            decision=DecisionValidation.APPROUVE,
            date_validation=datetime.utcnow()
        )
        db.add(validation)
        
        # Appeler la logique métier d'approbation directement
        res_besoin = val_service._traiter_approbation_besoin(
            besoin=besoin,
            validation=validation,
            id_validateur=dg.id,
            ordre="DG"
        )
        db.commit()
        db.refresh(caisse)
        
        print(f"Besoin traité. Statut du besoin : {besoin.statut.value}")
        print(f"Nouveau solde caisse après sortie : {caisse.solde_physique} USD")
        assert caisse.solde_physique == solde_initial + montant_entree - 1500.0, "Le solde physique n'a pas été décrémenté correctement pour le besoin !"
        print("[OK] Test d'acquisition/besoin reussi.")

        # 5. Test du workflow séquentiel d'amortissement
        print("\n--- 5. Test du workflow séquentiel d'amortissement ---")
        # Création d'un bien de test unique
        import time
        unique_suffix = int(time.time())
        bien = Bien(
            description=f"Ordinateur portable test {unique_suffix}",
            prix_acquisition=2000.0,
            date_acquisition=datetime.utcnow(),
            statut_comptable="ACTIF"
        )
        db.add(bien)
        db.flush()

        # Création d'un amortissement de test associé complet
        from app.models.amortissement import MethodeAmortissement
        amort = Amortissement(
            id_bien=bien.id_bien,
            exercice=datetime.utcnow().year,
            methode=MethodeAmortissement.LINEAIRE,
            valeur_origine=2000.0,
            duree_vie_comptable_ans=5,
            duree_vie_fiscale_ans=5,
            taux_comptable=20.0,
            taux_fiscal=20.0,
            annuite_comptable=800.00,
            annuite_fiscale=800.00,
            ecart_a_reintegrer=0.0,
            valeur_nette_comptable=1200.00,
            cumul_comptable=800.00,
            statut=StatutAmortissement.EN_COURS
        )
        db.add(amort)
        db.flush()

        # Création de l'écriture comptable associée
        ecriture = EcritureComptable(
            id_bien=bien.id_bien,
            id_amortissement=amort.id_amortissement,
            date_ecriture=datetime.utcnow(),
            exercice=datetime.utcnow().year,
            type_operation="DOTATION_AMORTISSEMENT",
            statut=StatutEcriture.BROUILLON,
            libelle="Dotation aux amortissements test",
            compte_debit="681",
            compte_credit="281",
            montant=800.00,
            validee=False,
            cree_par=comptable.id
        )
        db.add(ecriture)
        db.commit()

        workflow_service = AmortissementWorkflowService(db)
        
        # Étape 1 : Initialisation par le comptable
        print("Initialisation du workflow par le comptable...")
        workflow_service.initialiser_workflow(amort.id_amortissement, comptable.id)
        db.refresh(ecriture)
        print(f"Écriture statut_workflow : {ecriture.statut_workflow} (devrait être BROUILLON)")

        # Étape 2 : Vérification Caisse
        print("Vérification de la trésorerie par le caissier...")
        workflow_service.verifier_tresorerie(amort.id_amortissement, True, "Fonds vérifiés disponibles en caisse.", caissier.id)
        db.refresh(ecriture)
        print(f"Écriture statut_workflow après caisse : {ecriture.statut_workflow} (devrait être CAISSE_VALIDE)")

        # Étape 3 : Validation Décaissement par le DG
        print("Validation du décaissement et signature BSC par le DG...")
        prev_solde = caisse.solde_physique
        workflow_service.valider_decaissement(amort.id_amortissement, True, "Décaissement autorisé.", dg.id)
        db.refresh(ecriture)
        db.refresh(caisse)
        print(f"Écriture statut_workflow après DG : {ecriture.statut_workflow} (devrait être DG_VALIDE)")
        print(f"Vérification de la sortie de caisse : Ancien solde = {prev_solde} USD, Nouveau solde = {caisse.solde_physique} USD")
        assert caisse.solde_physique == prev_solde - 800.0, "Le solde n'a pas été décrémenté pour l'amortissement !"

        # Étape 4 : Validation finale et Verrouillage par le Comptable
        print("Validation finale et verrouillage par le comptable...")
        workflow_service.valider_ecriture(amort.id_amortissement, ecriture.piece_justificative_url, "Clôture et verrouillage définitif de l'amortissement.", comptable.id)
        db.refresh(ecriture)
        db.refresh(amort)
        print(f"Amortissement statut final : {amort.statut.value} (devrait être EN_COURS)")
        print(f"Amortissement verrouillé : {amort.est_verrouille} (devrait être True)")
        print(f"Écriture validée : {ecriture.validee} (devrait être True)")
        
        assert amort.est_verrouille is True, "L'amortissement n'est pas verrouillé !"
        assert ecriture.validee is True, "L'écriture n'est pas validée !"
        print("[OK] Test du workflow d'amortissement reussi.")

        # Nettoyage des données de test pour ne pas polluer
        print("\n--- Nettoyage des données de test ---")
        db.query(Validation).filter(Validation.id_besoin == besoin.id_besoin).delete()
        db.query(Besoin).filter(Besoin.id_besoin == besoin.id_besoin).delete()
        db.commit()
        print("Nettoyage terminé.")
        print("\n=== TOUS LES TESTS DU SCENARIO ONT REUSSI AVEC SUCCES ! ===")

    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] ERREUR LORS DU SCENARIO : {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_scenario()
