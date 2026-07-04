# backend/app/services/amortissement_workflow_service.py
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..models.workflow_amortissement import (
    WorkflowValidationAmortissement,
    EtapeWorkflowAmortissement,
    StatutWorkflowAmortissement
)
from ..models.amortissement import Amortissement, StatutAmortissement
from ..models.ecriture_comptable import EcritureComptable, StatutEcriture
from ..models.historique_statut_ecriture import HistoriqueStatutEcriture
from ..models.bien import Bien
from ..models.utilisateur import Utilisateur
from ..services.caisse_service import CaisseService
from ..services.notification_service import NotificationService
from ..models.notification import TypeNotificationEnum
import logging

logger = logging.getLogger(__name__)


class AmortissementWorkflowService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
        self.caisse_service = CaisseService(db)

    def initialiser_workflow(self, id_amortissement: int, user_id: int) -> WorkflowValidationAmortissement:
        """
        Étape 1 : Le comptable crée l'amortissement.
        Initialise l'étape 1 COMPTABLE (Approuvé) et prépare l'étape 2 CAISSE (En attente).
        """
        amortissement = self.db.query(Amortissement).filter(Amortissement.id_amortissement == id_amortissement).first()
        if not amortissement:
            raise ValueError("Amortissement non trouvé")

        # Supprimer tout workflow existant pour cet amortissement pour réinitialiser proprement
        self.db.query(WorkflowValidationAmortissement).filter(
            WorkflowValidationAmortissement.id_amortissement == id_amortissement
        ).delete()

        # Étape 1 : Comptable calcul
        step1 = WorkflowValidationAmortissement(
            id_amortissement=id_amortissement,
            etape=EtapeWorkflowAmortissement.COMPTABLE,
            statut=StatutWorkflowAmortissement.APPROUVE,
            id_validateur=user_id,
            date_validation=datetime.utcnow(),
            commentaire="Amortissement calculé et écriture en brouillon générée"
        )
        self.db.add(step1)

        # Étape 2 : Caisse attente
        step2 = WorkflowValidationAmortissement(
            id_amortissement=id_amortissement,
            etape=EtapeWorkflowAmortissement.CAISSE,
            statut=StatutWorkflowAmortissement.EN_ATTENTE
        )
        self.db.add(step2)

        # Mettre à jour l'écriture comptable associée à l'amortissement
        ecriture = self.db.query(EcritureComptable).filter(EcritureComptable.id_amortissement == id_amortissement).first()
        if ecriture:
            ecriture.statut = StatutEcriture.BROUILLON
            ecriture.statut_workflow = "BROUILLON"

        self.db.flush()

        # Notification pour la caisse
        try:
            self.notification_service.envoyer_notification_par_role(
                role_nom="CAISSE",
                type_notif=TypeNotificationEnum.AMORTISSEMENT_CALCULE,
                titre="Nouvel amortissement à vérifier",
                contenu=f"Un amortissement de {amortissement.annuite_comptable:,.2f} USD (#{amortissement.id_amortissement}) requiert votre vérification de trésorerie.",
                priorite="importante"
            )
        except Exception as e:
            logger.warning(f"Erreur notification caisse: {e}")

        return step1

    def verifier_tresorerie(self, id_amortissement: int, tresorerie_disponible: bool, commentaire: str, user_id: int) -> WorkflowValidationAmortissement:
        """
        Étape 2 : La CAISSE vérifie la trésorerie physique.
        """
        step_caisse = self.db.query(WorkflowValidationAmortissement).filter(
            WorkflowValidationAmortissement.id_amortissement == id_amortissement,
            WorkflowValidationAmortissement.etape == EtapeWorkflowAmortissement.CAISSE
        ).first()

        if not step_caisse:
            raise ValueError("Étape de validation caisse non trouvée pour cet amortissement.")

        if step_caisse.statut != StatutWorkflowAmortissement.EN_ATTENTE:
            raise ValueError("Cette étape a déjà été traitée.")

        amortissement = self.db.query(Amortissement).filter(Amortissement.id_amortissement == id_amortissement).first()
        if not amortissement:
            raise ValueError("Amortissement non trouvé")

        ecriture = self.db.query(EcritureComptable).filter(EcritureComptable.id_amortissement == id_amortissement).first()
        if not ecriture:
            raise ValueError("Écriture comptable associée non trouvée")

        # Vérification dynamique de la caisse
        tresorerie_info = self.caisse_service.verifier_tresorerie(float(amortissement.annuite_comptable))
        real_tresorerie_disponible = tresorerie_info["est_suffisante"]

        # Si les fonds réels sont insuffisants, l'opération est bloquée en EN_ATTENTE_FONDS
        if not real_tresorerie_disponible:
            tresorerie_disponible = False

        step_caisse.id_validateur = user_id
        step_caisse.date_validation = datetime.utcnow()
        step_caisse.commentaire = commentaire

        ancien_statut = ecriture.statut.value if hasattr(ecriture.statut, 'value') else str(ecriture.statut)

        if tresorerie_disponible:
            step_caisse.statut = StatutWorkflowAmortissement.APPROUVE
            ecriture.statut = StatutEcriture.CAISSE_VALIDE
            ecriture.statut_workflow = "CAISSE_VALIDE"
            ecriture.date_verification_caisse = datetime.utcnow()

            # Créer étape 3 DG en attente
            step_dg = WorkflowValidationAmortissement(
                id_amortissement=id_amortissement,
                etape=EtapeWorkflowAmortissement.DG,
                statut=StatutWorkflowAmortissement.EN_ATTENTE
            )
            self.db.add(step_dg)

            # Notification DG : DECAISSEMENT_A_VALIDER
            try:
                self.notification_service.envoyer_notification_par_role(
                    role_nom="DG",
                    type_notif=TypeNotificationEnum.AMORTISSEMENT_CALCULE,
                    titre="Décaissement à valider",
                    contenu=f"La caisse a confirmé la disponibilité des fonds pour l'amortissement {id_amortissement}. Veuillez autoriser le décaissement.",
                    priorite="importante"
                )
            except Exception as e:
                logger.warning(f"Erreur notification DG: {e}")
        else:
            step_caisse.statut = StatutWorkflowAmortissement.SUSPENDU
            amortissement.statut = StatutAmortissement.SUSPENDU
            ecriture.statut = StatutEcriture.EN_ATTENTE_FONDS
            ecriture.statut_workflow = "EN_ATTENTE_FONDS"
            ecriture.date_verification_caisse = datetime.utcnow()

            # Notification DG : TRESORERIE_INSUFFISANTE
            try:
                self.notification_service.envoyer_notification_par_role(
                    role_nom="DG",
                    type_notif=TypeNotificationEnum.AMORTISSEMENT_CALCULE,
                    titre="Réapprovisionnement nécessaire",
                    contenu=f"Fonds insuffisants en caisse pour l'amortissement {id_amortissement}. Réapprovisionnement nécessaire.",
                    priorite="importante"
                )
            except Exception as e:
                logger.warning(f"Erreur notification DG: {e}")

        # Journaliser le changement de statut
        log = HistoriqueStatutEcriture(
            id_ecriture=ecriture.id_ecriture,
            ancien_statut=ancien_statut,
            nouveau_statut=ecriture.statut_workflow,
            utilisateur_id=user_id,
            commentaire=commentaire or "Vérification trésorerie par la caisse."
        )
        self.db.add(log)
        self.db.flush()

        return step_caisse

    def valider_decaissement(self, id_amortissement: int, approuve: bool, motif: str, user_id: int) -> WorkflowValidationAmortissement:
        """
        Étape 3 : Le DG valide le décaissement et génère le Bon de Décaissement PDF.
        """
        step_dg = self.db.query(WorkflowValidationAmortissement).filter(
            WorkflowValidationAmortissement.id_amortissement == id_amortissement,
            WorkflowValidationAmortissement.etape == EtapeWorkflowAmortissement.DG
        ).first()

        if not step_dg:
            raise ValueError("Étape de validation DG non trouvée.")

        if step_dg.statut != StatutWorkflowAmortissement.EN_ATTENTE:
            raise ValueError("L'étape DG a déjà été traitée.")

        amortissement = self.db.query(Amortissement).filter(Amortissement.id_amortissement == id_amortissement).first()
        if not amortissement:
            raise ValueError("Amortissement introuvable.")

        ecriture = self.db.query(EcritureComptable).filter(EcritureComptable.id_amortissement == id_amortissement).first()
        if not ecriture:
            raise ValueError("Écriture associée non trouvée.")

        dg_user = self.db.query(Utilisateur).filter(Utilisateur.id == user_id).first()

        step_dg.id_validateur = user_id
        step_dg.date_validation = datetime.utcnow()
        step_dg.commentaire = motif

        ancien_statut = ecriture.statut.value if hasattr(ecriture.statut, 'value') else str(ecriture.statut)

        if approuve:
            # 1. Ordonner le décaissement dans la caisse
            caisse_res = self.caisse_service.ordonner_mouvement_caisse(
                type_mouvement="SORTIE",
                montant=float(amortissement.annuite_comptable),
                origine_type="AMORTISSEMENT",
                origine_id=id_amortissement,
                motif=f"Dotation aux amortissements exercice {amortissement.exercice} - Bien #{amortissement.id_bien}",
                beneficiaire="COMPTABILITE IMMOBILISATIONS",
                mode_reglement="ESPECES"
            )

            if not caisse_res["success"]:
                # Si le solde était insuffisant lors du décaissement réel
                ecriture.statut = StatutEcriture.EN_ATTENTE_FONDS
                ecriture.statut_workflow = "EN_ATTENTE_FONDS"
                step_dg.statut = StatutWorkflowAmortissement.SUSPENDU
                amortissement.statut = StatutAmortissement.SUSPENDU
                self.db.flush()
                raise ValueError("Décaissement impossible : solde de caisse insuffisant au moment du décaissement.")

            mouvement = caisse_res["mouvement"]
            pdf_url = mouvement.piece_jointe_url

            step_dg.statut = StatutWorkflowAmortissement.APPROUVE
            step_dg.bon_decaissement_pdf = pdf_url

            # 2. Mettre à jour l'écriture comptable
            ecriture.statut = StatutEcriture.DG_VALIDE
            ecriture.statut_workflow = "DG_VALIDE"
            ecriture.date_validation_dg = datetime.utcnow()
            ecriture.piece_justificative_url = pdf_url

            # Créer étape 4 COMPTABLE_VALIDATION
            step_comp = WorkflowValidationAmortissement(
                id_amortissement=id_amortissement,
                etape=EtapeWorkflowAmortissement.COMPTABLE_VALIDATION,
                statut=StatutWorkflowAmortissement.EN_ATTENTE
            )
            self.db.add(step_comp)

            # Notification COMPTABLE : ECRITURE_A_VALIDER
            try:
                self.notification_service.envoyer_notification_par_role(
                    role_nom="COMPTABLE",
                    type_notif=TypeNotificationEnum.AMORTISSEMENT_CALCULE,
                    titre="Écriture à valider",
                    contenu=f"Le décaissement pour l'amortissement {id_amortissement} est approuvé. Pièce justificative disponible. Veuillez valider l'écriture.",
                    priorite="importante"
                )
            except Exception as e:
                logger.warning(f"Erreur notification: {e}")
        else:
            step_dg.statut = StatutWorkflowAmortissement.REJETE
            amortissement.statut = StatutAmortissement.SUSPENDU
            ecriture.statut = StatutEcriture.REJETEE
            ecriture.statut_workflow = "REJETEE"

            # Notification COMPTABLE : AMORTISSEMENT_REJETE
            try:
                self.notification_service.envoyer_notification_par_role(
                    role_nom="COMPTABLE",
                    type_notif=TypeNotificationEnum.AMORTISSEMENT_CALCULE,
                    titre="Amortissement rejeté",
                    contenu=f"L'amortissement {id_amortissement} a été rejeté à l'étape DG. Motif : {motif}",
                    priorite="importante"
                )
            except Exception as e:
                logger.warning(f"Erreur notification: {e}")

        # Journaliser le changement de statut
        log = HistoriqueStatutEcriture(
            id_ecriture=ecriture.id_ecriture,
            ancien_statut=ancien_statut,
            nouveau_statut=ecriture.statut_workflow,
            utilisateur_id=user_id,
            commentaire=motif or "Décision du Directeur Général."
        )
        self.db.add(log)
        self.db.flush()

        return step_dg

    def valider_ecriture(self, id_amortissement: int, piece_justificative_url: Optional[str], commentaire: Optional[str], user_id: int) -> WorkflowValidationAmortissement:
        """
        Étape 4 : Le COMPTABLE valide définitivement l'écriture et verrouille l'amortissement.
        """
        step_final = self.db.query(WorkflowValidationAmortissement).filter(
            WorkflowValidationAmortissement.id_amortissement == id_amortissement,
            WorkflowValidationAmortissement.etape == EtapeWorkflowAmortissement.COMPTABLE_VALIDATION
        ).first()

        if not step_final:
            raise ValueError("Étape de validation finale comptable non trouvée.")

        if step_final.statut != StatutWorkflowAmortissement.EN_ATTENTE:
            raise ValueError("L'écriture a déjà été validée ou traitée.")

        amortissement = self.db.query(Amortissement).filter(Amortissement.id_amortissement == id_amortissement).first()
        if not amortissement:
            raise ValueError("Amortissement introuvable.")

        ecriture = self.db.query(EcritureComptable).filter(EcritureComptable.id_amortissement == id_amortissement).first()
        if not ecriture:
            raise ValueError("Écriture associée non trouvée.")

        # RÈGLE R6: L'écriture comptable ne peut être validée que si statut_workflow == DG_VALIDE
        if ecriture.statut_workflow != "DG_VALIDE":
            raise ValueError("L'écriture doit être en statut DG_VALIDE avant de pouvoir être validée.")

        # RÈGLE R5: Un BSC ne peut être généré sans pièce justificative attachée
        if not ecriture.piece_justificative_url and not piece_justificative_url:
            raise ValueError("Une pièce justificative (Bon de décaissement) est obligatoire.")

        step_final.id_validateur = user_id
        step_final.date_validation = datetime.utcnow()
        step_final.statut = StatutWorkflowAmortissement.APPROUVE
        step_final.commentaire = commentaire
        if piece_justificative_url:
            step_final.piece_justificative_url = piece_justificative_url

        ancien_statut = ecriture.statut.value if hasattr(ecriture.statut, 'value') else str(ecriture.statut)

        # Mettre à jour l'écriture comptable associée
        ecriture.validee = True
        ecriture.statut = StatutEcriture.VALIDEE
        ecriture.statut_workflow = "VALIDEE"
        ecriture.verrouille_definitivement = True
        if piece_justificative_url:
            ecriture.piece_justificative_url = piece_justificative_url

        # Verrouillage définitif de l'amortissement
        amortissement.verrouiller(utilisateur_id=user_id, raison=commentaire or "Validation définitive du workflow.")
        amortissement.statut = StatutAmortissement.EN_COURS

        # Journaliser le changement de statut
        log = HistoriqueStatutEcriture(
            id_ecriture=ecriture.id_ecriture,
            ancien_statut=ancien_statut,
            nouveau_statut="VALIDEE",
            utilisateur_id=user_id,
            commentaire=commentaire or "Validation finale du comptable et verrouillage de l'amortissement."
        )
        self.db.add(log)
        self.db.flush()

        # Notification de fin : AMORTISSEMENT_VALIDE
        try:
            self.notification_service.envoyer_notification_par_role(
                role_nom="COMPTABLE",
                type_notif=TypeNotificationEnum.AMORTISSEMENT_CALCULE,
                titre="Amortissement verrouillé",
                contenu=f"L'amortissement {id_amortissement} a été validé et verrouillé définitivement.",
                priorite="importante"
            )
        except Exception as e:
            logger.warning(f"Erreur notification finale: {e}")

        return step_final

    def get_workflow_status(self, id_amortissement: int) -> Dict[str, Any]:
        """
        Récupère l'historique complet et le statut actuel du workflow pour un amortissement.
        """
        validations = self.db.query(WorkflowValidationAmortissement).filter(
            WorkflowValidationAmortissement.id_amortissement == id_amortissement
        ).order_by(WorkflowValidationAmortissement.id_workflow.asc()).all()

        if not validations:
            return {
                "id_amortissement": id_amortissement,
                "etape_actuelle": "NON_INITIALISE",
                "statut_global": "EN_ATTENTE",
                "historique_validations": []
            }

        derniere = validations[-1]
        statut_global = derniere.statut.value if hasattr(derniere.statut, 'value') else str(derniere.statut)
        etape_actuelle = derniere.etape.value if hasattr(derniere.etape, 'value') else str(derniere.etape)

        if derniere.etape == EtapeWorkflowAmortissement.COMPTABLE_VALIDATION and derniere.statut == StatutWorkflowAmortissement.APPROUVE:
            statut_global = "VALIDE_DEFINITIF"

        historique = []
        for v in validations:
            val_name = None
            if v.id_validateur:
                user_obj = self.db.query(Utilisateur).filter(Utilisateur.id == v.id_validateur).first()
                if user_obj:
                    val_name = user_obj.nom_complet
            
            historique.append({
                "id_workflow": v.id_workflow,
                "etape": v.etape.value if hasattr(v.etape, 'value') else str(v.etape),
                "statut": v.statut.value if hasattr(v.statut, 'value') else str(v.statut),
                "id_validateur": v.id_validateur,
                "validateur_nom": val_name,
                "date_validation": v.date_validation.isoformat() if v.date_validation else None,
                "commentaire": v.commentaire,
                "piece_justificative_url": v.piece_justificative_url,
                "bon_decaissement_pdf": v.bon_decaissement_pdf
            })

        return {
            "id_amortissement": id_amortissement,
            "etape_actuelle": etape_actuelle,
            "statut_global": statut_global,
            "historique_validations": historique
        }
