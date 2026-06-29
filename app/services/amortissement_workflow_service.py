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
from ..models.bien import Bien
from ..models.utilisateur import Utilisateur
from ..utils.pdf_generator import generer_bon_decaissement_pdf
from .notification_service import NotificationService
from ..models.notification import TypeNotificationEnum
import logging

logger = logging.getLogger(__name__)


class AmortissementWorkflowService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

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
            commentaire="Amortissement calculé et écriture en brouillon générée (Montant verrouillé)"
        )
        self.db.add(step1)

        # Étape 2 : Caisse attente
        step2 = WorkflowValidationAmortissement(
            id_amortissement=id_amortissement,
            etape=EtapeWorkflowAmortissement.CAISSE,
            statut=StatutWorkflowAmortissement.EN_ATTENTE
        )
        self.db.add(step2)
        self.db.flush()

        # Notification pour la caisse
        try:
            self._notifier_role(
                role="CAISSE",
                titre="Nouvel amortissement à vérifier",
                message=f"Un amortissement de {amortissement.annuite_comptable:,.2f} USD (#{amortissement.id_amortissement}) requiert votre vérification de trésorerie."
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

        step_caisse.id_validateur = user_id
        step_caisse.date_validation = datetime.utcnow()
        step_caisse.commentaire = commentaire

        if tresorerie_disponible:
            step_caisse.statut = StatutWorkflowAmortissement.APPROUVE
            
            # Créer étape 3 DG
            step_dg = WorkflowValidationAmortissement(
                id_amortissement=id_amortissement,
                etape=EtapeWorkflowAmortissement.DG,
                statut=StatutWorkflowAmortissement.EN_ATTENTE
            )
            self.db.add(step_dg)
            self.db.flush()

            # Notifications (OUI - Fonds disponibles)
            try:
                msg = f"VÉRIFICATION CAISSE : OUI (Fonds disponibles) - Amortissement #{amortissement.id_amortissement} ({amortissement.annuite_comptable:,.2f} USD). Observation : {commentaire or 'Fonds vérifiés.'}"
                self._notifier_role(role="DG", titre="Trésorerie Caisse : FONDS DISPONIBLES (OUI)", message=msg)
                self._notifier_role(role="COMPTABLE", titre="Trésorerie Caisse : FONDS DISPONIBLES (OUI)", message=msg)
            except Exception as e:
                logger.warning(f"Erreur notification Caisse OUI: {e}")
        else:
            step_caisse.statut = StatutWorkflowAmortissement.SUSPENDU
            if amortissement:
                amortissement.statut = StatutAmortissement.SUSPENDU
            self.db.flush()

            # Notifications (NON - Fonds insuffisants)
            try:
                msg = f"VÉRIFICATION CAISSE : NON (Fonds insuffisants) - Amortissement #{amortissement.id_amortissement} ({amortissement.annuite_comptable:,.2f} USD). Motif : {commentaire or 'Insuffisance de trésorerie.'}"
                self._notifier_role(role="COMPTABLE", titre="Trésorerie Caisse : FONDS INSUFFISANTS (NON)", message=msg)
                self._notifier_role(role="DG", titre="Trésorerie Caisse : FONDS INSUFFISANTS (NON)", message=msg)
            except Exception as e:
                logger.warning(f"Erreur notification Caisse NON: {e}")

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

        bien = self.db.query(Bien).filter(Bien.id_bien == amortissement.id_bien).first()
        dg_user = self.db.query(Utilisateur).filter(Utilisateur.id == user_id).first()

        step_dg.id_validateur = user_id
        step_dg.date_validation = datetime.utcnow()
        step_dg.commentaire = motif

        if approuve:
            step_dg.statut = StatutWorkflowAmortissement.APPROUVE
            
            # Génération du PDF Bon de Décaissement
            try:
                pdf_bytes = generer_bon_decaissement_pdf(amortissement, bien, dg_user, motif)
                
                # Sauvegarde sur disque (dossier static / uploads)
                upload_dir = os.path.join(os.getcwd(), "static", "bons_decaissement")
                os.makedirs(upload_dir, exist_ok=True)
                filename = f"bon_decaissement_{amortissement.id_amortissement}_{int(datetime.utcnow().timestamp())}.pdf"
                filepath = os.path.join(upload_dir, filename)
                
                with open(filepath, "wb") as f:
                    f.write(pdf_bytes)
                
                pdf_url = f"/static/bons_decaissement/{filename}"
                step_dg.bon_decaissement_pdf = pdf_url
            except Exception as e:
                logger.error(f"Erreur lors de la génération du PDF Bon de Décaissement: {e}")

            # Créer étape 4 COMPTABLE_VALIDATION
            step_comp = WorkflowValidationAmortissement(
                id_amortissement=id_amortissement,
                etape=EtapeWorkflowAmortissement.COMPTABLE_VALIDATION,
                statut=StatutWorkflowAmortissement.EN_ATTENTE
            )
            self.db.add(step_comp)
            self.db.flush()

            # Notification au Comptable
            try:
                self._notifier_role(
                    role="COMPTABLE",
                    titre="Écriture prête à valider",
                    message=f"Le décaissement pour l'amortissement #{amortissement.id_amortissement} a été approuvé par le DG. Le Bon de décaissement est joint. Veuillez procéder à la validation finale de l'écriture."
                )
            except Exception as e:
                logger.warning(f"Erreur notification: {e}")
        else:
            step_dg.statut = StatutWorkflowAmortissement.REJETE
            amortissement.statut = StatutAmortissement.SUSPENDU
            self.db.flush()

            # Notification rejet
            try:
                self._notifier_role(
                    role="COMPTABLE",
                    titre="Décaissement rejeté par le DG",
                    message=f"Le décaissement pour l'amortissement #{amortissement.id_amortissement} a été rejeté par le DG. Motif : {motif}"
                )
            except Exception as e:
                logger.warning(f"Erreur notification: {e}")

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

        step_final.id_validateur = user_id
        step_final.date_validation = datetime.utcnow()
        step_final.statut = StatutWorkflowAmortissement.APPROUVE
        step_final.commentaire = commentaire
        step_final.piece_justificative_url = piece_justificative_url

        # Mettre à jour l'écriture comptable associée
        ecriture = self.db.query(EcritureComptable).filter(EcritureComptable.id_amortissement == id_amortissement).first()
        if ecriture:
            ecriture.validee = True
            ecriture.statut = StatutEcriture.VALIDEE
            if piece_justificative_url:
                ecriture.piece_justificative_url = piece_justificative_url

        # Verrouillage définitif de l'amortissement
        amortissement.est_verrouille = True
        amortissement.date_verrouillage = datetime.utcnow()
        amortissement.verrouille_par_id = user_id
        amortissement.raison_verrouillage = commentaire or "Validation finale du workflow séquentiel COMPTABLE-CAISSE-DG-COMPTABLE"
        amortissement.statut = StatutAmortissement.EN_COURS

        self.db.flush()

        # Notification de fin
        try:
            self._notifier_role(
                role="COMPTABLE",
                titre="Amortissement validé et verrouillé",
                message=f"L'amortissement #{amortissement.id_amortissement} a été entièrement validé et verrouillé définitivement en comptabilité."
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

        # Si la dernière étape est APPROUVE et qu'il s'agit de la validation finale, le workflow est complet
        if derniere.etape == EtapeWorkflowAmortissement.COMPTABLE_VALIDATION and derniere.statut == StatutWorkflowAmortissement.APPROUVE:
            statut_global = "VALIDE_DEFINITIF"

        historique = []
        for v in validations:
            val_name = None
            if v.id_validateur:
                user_obj = v.validateur or self.db.query(Utilisateur).filter(Utilisateur.id == v.id_validateur).first()
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

    def _notifier_role(self, role: str, titre: str, message: str):
        """Helper pour notifier tous les utilisateurs ayant un rôle donné."""
        try:
            self.notification_service.envoyer_notification_par_role(
                role_nom=role,
                type_notif=TypeNotificationEnum.AMORTISSEMENT_CALCULE,
                titre=titre,
                contenu=message,
                priorite="importante"
            )
        except Exception as e:
            logger.warning(f"Erreur envoi notification pour role {role}: {e}")
