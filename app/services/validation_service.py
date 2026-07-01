# app/services/validation_service.py
from decimal import Decimal
from datetime import datetime
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from ..models.panne import Panne

from ..models.validation import Validation, OrdreValidation, DecisionValidation, TypeValidation
from ..models.besoin import Besoin, StatutBesoin
from ..models.bien import Bien, EtatBien
from ..models.cession import Cession, StatutCession
from ..models.amortissement import Amortissement, StatutAmortissement
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..models.budget import Budget
from ..models.ecriture_comptable import EcritureComptable, TypeOperationEnum, StatutEcriture
from ..services.notification_service import NotificationService, TypeNotificationEnum
from ..services.budget_service import BudgetService
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


class ValidationService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
        self.budget_service = BudgetService(db)
        self.audit_service = AuditService(db)

    def _get_utilisateurs_par_roles(self, *roles: str) -> List[Utilisateur]:
        """Récupère les utilisateurs ayant un des rôles donnés."""
        roles_upper = [role.upper() for role in roles]
        return (
            self.db.query(Utilisateur)
            .join(Role)
            .filter(func.upper(Role.nom).in_(roles_upper))
            .all()
        )

    def _get_prochain_validateur(self, etape_actuelle: OrdreValidation) -> OrdreValidation:
        """Détermine le prochain validateur dans le workflow."""
        ordre_etapes = [OrdreValidation.COMPTABLE, OrdreValidation.CAISSE, OrdreValidation.DG]
        try:
            index = ordre_etapes.index(etape_actuelle)
            if index < len(ordre_etapes) - 1:
                return ordre_etapes[index + 1]
        except ValueError:
            pass
        return None

    def _get_ordre_enum(self, ordre: str) -> OrdreValidation:
        """Récupère l'enum OrdreValidation."""
        try:
            return OrdreValidation[ordre.upper()]
        except KeyError:
            raise ValueError(f"Ordre de validation invalide: {ordre}")

    def _get_decision_enum(self, decision: str) -> DecisionValidation:
        """Récupère l'enum DecisionValidation."""
        try:
            return DecisionValidation[decision.upper()]
        except KeyError:
            raise ValueError(f"Décision invalide: {decision}")

    def _get_bien_designation(self, bien):
        """Récupère la désignation d'un bien."""
        if not bien:
            return None
        return f"{getattr(bien, 'marque', None) or getattr(bien, 'fabricant', None) or ''} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"

    # ============================================================
    # WORKFLOW BESOIN – AVEC TRANSACTION ACID
    # ============================================================

    def valider_besoin(
        self,
        besoin_id: int,
        id_validateur: int,
        ordre_validateur: str,
        decision: str,
        commentaire: str = None,
        piece_justificative_url: str = None
    ) -> dict:
        """
        Valide ou rejette un besoin dans le workflow séquentiel.
        Workflow: BROUILLON/EN_VALIDATION → DG → COMPTABLE → CAISSE → APPROUVEE
        
        ✅ TRANSACTION ACID englobante
        ✅ Budget engagé dans la transaction
        ✅ Verrous pessimistes sur les lignes
        """
        ordre_enum = self._get_ordre_enum(ordre_validateur)
        decision_enum = self._get_decision_enum(decision)

        try:
            # ============================================================
            # 🔐 TRANSACTION ACID UNIQUE
            # ============================================================
            with self.db.begin():
                # 1. Récupérer le besoin avec verrou pessimiste
                besoin = self.db.query(Besoin).filter(
                    Besoin.id_besoin == besoin_id
                ).with_for_update().first()

                if not besoin:
                    raise ValueError("Besoin non trouvé")

                # 2. Vérifier que le besoin est en attente de ce validateur
                if not self._est_en_attente_de(besoin, ordre_validateur):
                    raise ValueError(f"Ce besoin n'est pas en attente de validation par {ordre_validateur}")

                # 3. Créer la validation
                validation = Validation(
                    id_besoin=besoin_id,
                    id_validateur=id_validateur,
                    ordre_validateur=ordre_enum,
                    type_validation=TypeValidation.BESOIN,
                    decision=decision_enum,
                    commentaire=commentaire,
                    piece_justificative_url=piece_justificative_url,
                    date_validation=datetime.utcnow()
                )
                self.db.add(validation)

                # 4. Traiter la décision
                if decision_enum == DecisionValidation.REJETE:
                    result = self._traiter_rejet_besoin(besoin, validation, id_validateur, ordre_validateur, commentaire)
                else:
                    result = self._traiter_approbation_besoin(besoin, validation, id_validateur, ordre_validateur)

                # 5. Mettre à jour le besoin
                self.db.add(besoin)

        except SQLAlchemyError as e:
            logger.error(f"Erreur transaction validation besoin {besoin_id}: {e}")
            raise ValueError(f"Échec de la validation : {str(e)}")
        except ValueError as e:
            raise

        # Rafraîchir et journaliser
        self.db.refresh(besoin)
        self.audit_service.log_action(
            user_id=id_validateur,
            table_name="besoins",
            record_id=besoin_id,
            action=f"VALIDATION_{decision}",
            nouvelles_valeurs={"statut": besoin.statut.value, "validation_id": validation.id_validation}
        )

        return result

    def _est_en_attente_de(self, besoin: Besoin, ordre: str) -> bool:
        """
        Vérifie si le besoin est en attente d'un ordre donné.
        Workflow: COMPTABLE → CAISSE → DG
        """
        mapping = {
            "COMPTABLE": [StatutBesoin.BROUILLON, StatutBesoin.EN_VALIDATION],
            "CAISSE": [StatutBesoin.COMPTABLE_VALIDE],
            "DG": [StatutBesoin.CAISSE_VALIDE]
        }
        attente_statuts = mapping.get(ordre.upper(), [])
        return besoin.statut in attente_statuts

    def _traiter_rejet_besoin(self, besoin: Besoin, validation: Validation,
                              id_validateur: int, ordre: str, motif: str):
        """Traite le rejet d'un besoin."""
        besoin.statut = StatutBesoin.REJETE

        # Si budget déjà engagé, le libérer dans la même transaction
        if besoin.id_budget and besoin.montant_total and besoin.montant_total > 0:
            try:
                self.budget_service.liberer_montant(
                    budget_id=besoin.id_budget,
                    montant=besoin.montant_total,
                    commit=False
                )
            except Exception as e:
                logger.warning(f"Libération budget échouée: {e}")

        # Notifier le technicien
        panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first() if besoin.id_panne else None
        id_technicien = panne.id_technicien if panne else None

        if id_technicien:
            self.notification_service.envoyer_notification(
                ids_destinataires=id_technicien,
                type_notif=TypeNotificationEnum.BESOIN_REJETE,
                titre=f"❌ Besoin rejeté - {besoin.numero_demande}",
                contenu=f"Votre demande {besoin.numero_demande} a été rejetée par {ordre}. Motif: {motif or 'Non spécifié'}",
                lien=f"/pannes/{besoin.id_panne}"
            )

        return {
            "id_besoin": besoin.id_besoin,
            "numero_demande": besoin.numero_demande,
            "statut": besoin.statut.value,
            "decision": "REJETE",
            "motif": motif
        }

    def _traiter_approbation_besoin(self, besoin: Besoin, validation: Validation,
                                    id_validateur: int, ordre: str):
        """
        Traite l'approbation d'un besoin.
        Workflow: COMPTABLE (Budget) → CAISSE (Trésorerie) → DG (Décaissement & Approbation finale)
        """
        ordre_enum = self._get_ordre_enum(ordre)

        if ordre_enum == OrdreValidation.COMPTABLE:
            # ÉTAPE 1 : COMPTABLE (Vérification du budget disponible)
            centre_cout = self._get_centre_cout_besoin(besoin)
            annee = datetime.utcnow().year

            verification = self.budget_service.verifier_disponibilite(
                centre_cout,
                annee,
                besoin.montant_total
            )

            if not verification.est_disponible:
                validation.decision = DecisionValidation.REJETE
                validation.motif_rejet = f"Solde budgétaire Insuffisant: {verification.message}"
                besoin.statut = StatutBesoin.REJETE
                return {
                    "id_besoin": besoin.id_besoin,
                    "statut": besoin.statut.value,
                    "decision": "REJETE",
                    "motif": validation.motif_rejet
                }

            # Engagement du budget DANS LA TRANSACTION (si budget OK)
            engagement = self.budget_service.engager_montant(
                centre_cout=centre_cout,
                exercice=annee,
                montant=besoin.montant_total,
                validation_id=validation.id_validation,
                commit=False
            )
            if engagement and hasattr(engagement, "id_budget"):
                besoin.id_budget = engagement.id_budget

            besoin.statut = StatutBesoin.COMPTABLE_VALIDE

        elif ordre_enum == OrdreValidation.CAISSE:
            # ÉTAPE 2 : CAISSE (Vérification de la trésorerie physique disponible)
            from ..services.caisse_service import CaisseService
            caisse_service = CaisseService(self.db)
            tresorerie = caisse_service.verifier_tresorerie(besoin.montant_total)

            if not tresorerie["est_suffisante"]:
                validation.decision = DecisionValidation.REJETE
                validation.motif_rejet = f"Fonds caisse Insuffisant: {tresorerie['message']}"
                besoin.statut = StatutBesoin.REJETE
                return {
                    "id_besoin": besoin.id_besoin,
                    "statut": besoin.statut.value,
                    "decision": "REJETE",
                    "motif": validation.motif_rejet
                }

            besoin.statut = StatutBesoin.CAISSE_VALIDE

        elif ordre_enum == OrdreValidation.DG:
            # ÉTAPE 3 : DG (Validation finale stratégique)
            besoin.statut = StatutBesoin.APPROUVEE

            # Générer le bon de décaissement (numérique)
            bon_decaissement = self._generer_bon_decaissement(besoin, id_validateur)

            # Ordonner le mouvement de caisse réel (sortie)
            from .caisse_service import CaisseService
            caisse_service = CaisseService(self.db)
            caisse_service.ordonner_mouvement_caisse(
                type_mouvement="SORTIE",
                montant=float(besoin.montant_total),
                origine_type="BESOIN",
                origine_id=besoin.id_besoin,
                motif=f"Décaissement besoin {besoin.numero_demande} : {getattr(besoin, 'observations', '') or ''}"
            )

            # Notifier le caissier pour le paiement effectif
            caissiers = self._get_utilisateurs_par_roles("CAISSE")
            for caissier in caissiers:
                self.notification_service.envoyer_notification(
                    ids_destinataires=caissier.id,
                    type_notif=TypeNotificationEnum.FOURNITURE_EN_ATTENTE,
                    titre=f"💰 Bon de décaissement généré - {besoin.numero_demande}",
                    contenu=f"Le besoin {besoin.numero_demande} a reçu la validation finale de la DG. Montant: {besoin.montant_total:,.0f} USD. Veuillez procéder au décaissement.",
                    lien=f"/besoins/{besoin.id_besoin}"
                )

        # Notifier le prochain validateur
        self._notifier_prochain_validateur(besoin, ordre, is_rejet=False)

        return {
            "id_besoin": besoin.id_besoin,
            "numero_demande": besoin.numero_demande,
            "statut": besoin.statut.value,
            "decision": "APPROUVE"
        }

    def _get_centre_cout_besoin(self, besoin: Besoin) -> str:
        """Récupère le centre de coût d'un besoin depuis le besoin ou la panne/bien."""
        if besoin.centre_cout and besoin.centre_cout.strip():
            return besoin.centre_cout.strip()
        if besoin.id_panne:
            panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first()
            if panne and panne.bien and getattr(panne.bien, 'centre_cout', None):
                return panne.bien.centre_cout
        return "SERVICE_GENERAL"

    def _generer_bon_decaissement(self, besoin: Besoin, validateur_id: int) -> dict:
        """Génère un bon de décaissement numérique."""
        ecriture = EcritureComptable(
            id_bien=None,
            date_ecriture=datetime.utcnow(),
            exercice=datetime.utcnow().year,
            type_operation=TypeOperationEnum.DECAISSEMENT,
            statut=StatutEcriture.EN_ATTENTE_PAIEMENT,
            libelle=f"Bon de décaissement - Besoin {besoin.numero_demande}",
            compte_debit="654",
            compte_credit="512",
            montant=float(besoin.montant_total),
            validee=False,
            cree_par=validateur_id
        )
        self.db.add(ecriture)
        self.db.flush()

        return {
            "id_ecriture": ecriture.id_ecriture,
            "numero_bon": f"BD-{besoin.numero_demande}-{datetime.utcnow().strftime('%Y%m%d')}",
            "montant": float(besoin.montant_total),
            "date": datetime.utcnow().isoformat(),
            "statut": "EN_ATTENTE_PAIEMENT"
        }

    def _notifier_prochain_validateur(self, besoin: Besoin, ordre_actuel: str, is_rejet: bool = False):
        """Notifie le prochain validateur."""
        if is_rejet:
            return

        ordre_enum = self._get_ordre_enum(ordre_actuel)
        prochain = self._get_prochain_validateur(ordre_enum)

        if not prochain:
            return

        validateurs = self._get_utilisateurs_par_roles(prochain.value)

        if prochain == OrdreValidation.DG:
            titre = f"📋 Besoin à valider - {besoin.numero_demande}"
            contenu = f"La demande {besoin.numero_demande} est en attente de validation par la DG. Montant: {besoin.montant_total:,.0f} USD"
        elif prochain == OrdreValidation.COMPTABLE:
            titre = f"📋 Besoin à valider - {besoin.numero_demande}"
            contenu = f"La demande {besoin.numero_demande} est en attente de validation par le Comptable. Montant: {besoin.montant_total:,.0f} USD"
        elif prochain == OrdreValidation.CAISSE:
            titre = f"💰 Besoin à valider - {besoin.numero_demande}"
            contenu = f"La demande {besoin.numero_demande} est en attente de validation par la Caisse. Montant: {besoin.montant_total:,.0f} USD"
        else:
            return

        for validateur in validateurs:
            self.notification_service.envoyer_notification(
                ids_destinataires=validateur.id,
                type_notif=TypeNotificationEnum.BESOIN_VALIDE,
                titre=titre,
                contenu=contenu,
                lien=f"/validations/besoins/{besoin.id_besoin}"
            )

    # ============================================================
    # WORKFLOW CESSION – AVEC TRANSACTION ACID ET CEDE DIFFÉRÉ
    # ============================================================

    def valider_cession(
        self,
        cession_id: int,
        id_validateur: int,
        ordre_validateur: str,
        decision: str,
        commentaire: str = None,
        piece_justificative_url: str = None
    ) -> dict:
        """
        Valide ou rejette une cession dans le workflow séquentiel.
        
        🔴 CRITIQUE : Le statut CEDE n'est appliqué qu'après validation de l'encaissement
        Workflow: Demande → Comptable → Caissier → DG
        """
        ordre_enum = self._get_ordre_enum(ordre_validateur)
        decision_enum = self._get_decision_enum(decision)

        try:
            with self.db.begin():
                # 1. Récupérer la cession avec verrou
                cession = self.db.query(Cession).filter(
                    Cession.id_cession == cession_id
                ).with_for_update().first()

                if not cession:
                    raise ValueError("Cession non trouvée")

                # 2. Récupérer le bien avec verrou
                bien = self.db.query(Bien).filter(
                    Bien.id_bien == cession.id_bien
                ).with_for_update().first()

                if not bien:
                    raise ValueError(f"Bien associé à la cession non trouvé")

                # 3. Vérifier que la cession est dans le bon statut
                if not self._est_en_attente_de_cession(cession, ordre_validateur):
                    raise ValueError(f"Cette cession n'est pas en attente de validation par {ordre_validateur}")

                # 4. Créer la validation
                validation = Validation(
                    id_bien=cession.id_bien,
                    id_validateur=id_validateur,
                    ordre_validateur=ordre_enum,
                    type_validation=TypeValidation.CESSION,
                    decision=decision_enum,
                    commentaire=commentaire,
                    piece_justificative_url=piece_justificative_url,
                    date_validation=datetime.utcnow()
                )
                self.db.add(validation)

                # 5. Traiter la décision
                if decision_enum == DecisionValidation.REJETE:
                    result = self._traiter_rejet_cession(cession, validation, id_validateur, ordre_validateur, commentaire)
                else:
                    result = self._traiter_approbation_cession(cession, bien, validation, id_validateur, ordre_validateur)

                self.db.add(cession)
                self.db.add(bien)

        except SQLAlchemyError as e:
            logger.error(f"Erreur transaction validation cession {cession_id}: {e}")
            raise ValueError(f"Échec de la validation : {str(e)}")

        self.db.refresh(cession)
        self.audit_service.log_action(
            user_id=id_validateur,
            table_name="cessions",
            record_id=cession_id,
            action=f"VALIDATION_{decision}",
            nouvelles_valeurs={"statut": cession.statut.value, "validation_id": validation.id_validation}
        )

        return result

    def _est_en_attente_de_cession(self, cession: Cession, ordre: str) -> bool:
        """Vérifie si la cession est en attente d'un ordre donné."""
        mapping = {
            "COMPTABLE": StatutCession.EN_ATTENTE_VALIDATION,
            "CAISSE": StatutCession.EN_COURS,
            "DG": StatutCession.EN_COURS
        }
        return cession.statut == mapping.get(ordre.upper()) or cession.statut == StatutCession.EN_ATTENTE_VALIDATION

    def _traiter_rejet_cession(self, cession: Cession, validation: Validation,
                               id_validateur: int, ordre: str, motif: str):
        """Traite le rejet d'une cession."""
        cession.statut = StatutCession.REJETEE
        cession.motif = motif

        self.notification_service.envoyer_notification(
            ids_destinataires=cession.cree_par if cession.cree_par else None,
            type_notif=TypeNotificationEnum.BESOIN_REJETE,
            titre=f"❌ Cession rejetée - Bien #{cession.id_bien}",
            contenu=f"La demande de cession a été rejetée par {ordre}. Motif: {motif or 'Non spécifié'}",
            lien=f"/cessions/{cession.id_cession}"
        )

        return {
            "id_cession": cession.id_cession,
            "statut": cession.statut.value,
            "decision": "REJETE",
            "motif": motif
        }

    def _traiter_approbation_cession(self, cession: Cession, bien: Bien,
                                     validation: Validation, id_validateur: int, ordre: str):
        """Traite l'approbation d'une cession."""
        ordre_enum = self._get_ordre_enum(ordre)

        if ordre_enum == OrdreValidation.COMPTABLE:
            cession.statut = StatutCession.EN_COURS
            cession.date_validation_comptable = datetime.utcnow()
            cession.id_validateur_comptable = id_validateur

        elif ordre_enum == OrdreValidation.CAISSE:
            # 🔴 MOMENT CRITIQUE : Le caissier valide l'encaissement
            cession.statut = StatutCession.EN_COURS
            cession.date_validation_caissier = datetime.utcnow()
            cession.id_validateur_caissier = id_validateur

            # ✅ À CE MOMENT PRÉCIS, le bien passe à CEDE
            bien.statut_comptable = "CEDE"
            bien.date_sortie = datetime.utcnow()

            # Ordonner le mouvement de caisse réel (entrée)
            from .caisse_service import CaisseService
            caisse_service = CaisseService(self.db)
            caisse_service.ordonner_mouvement_caisse(
                type_mouvement="ENTREE",
                montant=float(cession.prix_cession or 0.0),
                origine_type="CESSION",
                origine_id=cession.id_cession,
                motif=f"Encaissement cession bien #{bien.id_bien} : {bien.nom_bien or bien.designation or ''}",
                beneficiaire=cession.acheteur or "Acheteur externe"
            )

            # Journaliser l'événement
            self.audit_service.log_action(
                user_id=id_validateur,
                table_name="biens",
                record_id=bien.id_bien,
                action="CEDE_APRES_ENCAISSEMENT",
                nouvelles_valeurs={
                    "statut_comptable": "CEDE",
                    "date_sortie": bien.date_sortie.isoformat(),
                    "cession_id": cession.id_cession
                }
            )

        elif ordre_enum == OrdreValidation.DG:
            # Dernière validation
            cession.statut = StatutCession.ACCORDEE
            cession.date_validation_dg = datetime.utcnow()
            cession.date_validation_finale = datetime.utcnow()
            cession.id_validateur_dg = id_validateur

        # Notifier le prochain validateur
        self._notifier_prochain_validateur_cession(cession, ordre)

        return {
            "id_cession": cession.id_cession,
            "statut": cession.statut.value,
            "decision": "APPROUVE"
        }

    def _notifier_prochain_validateur_cession(self, cession: Cession, ordre_actuel: str):
        """Notifie le prochain validateur pour une cession."""
        ordre_enum = self._get_ordre_enum(ordre_actuel)
        prochain = self._get_prochain_validateur(ordre_enum)

        if not prochain:
            return

        validateurs = self._get_utilisateurs_par_roles(prochain.value)

        for validateur in validateurs:
            self.notification_service.envoyer_notification(
                ids_destinataires=validateur.id,
                type_notif=TypeNotificationEnum.BESOIN_VALIDE,
                titre=f"📋 Cession à valider - Bien #{cession.id_bien}",
                contenu=f"La demande de cession est en attente de validation par {prochain.value}.",
                lien=f"/cessions/{cession.id_cession}"
            )

    # ============================================================
    # WORKFLOW AMORTISSEMENT – AVEC TRANSACTION ACID
    # ============================================================

    def valider_amortissement(
        self,
        amortissement_id: int,
        id_validateur: int,
        decision: str,
        commentaire: str = None,
        piece_justificative_url: str = None
    ) -> dict:
        """
        Valide ou rejette un amortissement après vérification de trésorerie.
        """
        decision_enum = self._get_decision_enum(decision)

        try:
            with self.db.begin():
                amortissement = self.db.query(Amortissement).filter(
                    Amortissement.id_amortissement == amortissement_id
                ).with_for_update().first()

                if not amortissement:
                    raise ValueError("Amortissement non trouvé")

                if decision_enum == DecisionValidation.REJETE:
                    return self._traiter_rejet_amortissement(amortissement, id_validateur, commentaire)
                else:
                    return self._traiter_approbation_amortissement(amortissement, id_validateur, commentaire, piece_justificative_url)

        except SQLAlchemyError as e:
            logger.error(f"Erreur transaction validation amortissement {amortissement_id}: {e}")
            raise ValueError(f"Échec de la validation : {str(e)}")

    def _traiter_rejet_amortissement(self, amortissement: Amortissement, id_validateur: int, motif: str):
        """Traite le rejet d'un amortissement."""
        amortissement.statut = StatutAmortissement.SUSPENDU

        self.notification_service.envoyer_notification(
            ids_destinataires=id_validateur,
            type_notif=TypeNotificationEnum.ALERTE_STOCK,
            titre=f"⚠️ Amortissement rejeté - Exercice {amortissement.exercice}",
            contenu=f"L'amortissement a été rejeté. Motif: {motif or 'Non spécifié'}",
            lien=f"/amortissements/{amortissement.id_amortissement}"
        )

        return {
            "id_amortissement": amortissement.id_amortissement,
            "statut": amortissement.statut.value,
            "decision": "REJETE"
        }

    def _traiter_approbation_amortissement(self, amortissement: Amortissement, id_validateur: int,
                                           commentaire: str, piece_justificative_url: str):
        """Traite l'approbation d'un amortissement."""
        tresorerie = self.budget_service.verifier_tresorerie(
            Decimal(str(amortissement.annuite_comptable))
        )

        if not tresorerie["est_suffisante"]:
            amortissement.statut = StatutAmortissement.SUSPENDU

            dg_users = self._get_utilisateurs_par_roles("DG")
            for dg in dg_users:
                self.notification_service.envoyer_notification(
                    ids_destinataires=dg.id,
                    type_notif=TypeNotificationEnum.ALERTE_STOCK,
                    titre=f"💰 Trésorerie insuffisante - Amortissement {amortissement.exercice}",
                    contenu=f"La trésorerie est insuffisante pour l'amortissement. Manque: {tresorerie['manque']:,.0f} USD",
                    lien=f"/amortissements/{amortissement.id_amortissement}"
                )

            return {
                "id_amortissement": amortissement.id_amortissement,
                "statut": amortissement.statut.value,
                "decision": "SUSPENDU",
                "motif": "Trésorerie insuffisante"
            }

        amortissement.statut = StatutAmortissement.EN_COURS
        amortissement.date_validation = datetime.utcnow()

        from .comptabilite_service import ComptabiliteService
        comptabilite = ComptabiliteService(self.db, cree_par_id=id_validateur)

        bien = self.db.query(Bien).filter(Bien.id_bien == amortissement.id_bien).first()

        ecriture = comptabilite.generer_ecriture_dotation(amortissement, bien.type_bien if bien else "autre")

        ecriture.validee = True
        ecriture.statut = StatutEcriture.VALIDEE
        ecriture.date_validation = datetime.utcnow()
        ecriture.id_validateur = id_validateur

        if bien:
            cumul_actuel = float(bien.cumul_amortissement or 0)
            bien.cumul_amortissement = round(cumul_actuel + amortissement.annuite_comptable, 2)

        return {
            "id_amortissement": amortissement.id_amortissement,
            "id_ecriture": ecriture.id_ecriture,
            "statut": amortissement.statut.value,
            "decision": "APPROUVE"
        }

    # ============================================================
    # MÉTHODES UTILITAIRES AVEC LES BONNES VALEURS DE StatutBesoin
    # ============================================================

    def get_besoins_en_attente(self, role: str) -> List[dict]:
        """Récupère les besoins en attente de validation par un rôle."""
        besoins = []

        if role.upper() == "COMPTABLE":
            besoins = self.db.query(Besoin).filter(
                Besoin.statut.in_([StatutBesoin.BROUILLON, StatutBesoin.EN_VALIDATION])
            ).all()
        elif role.upper() == "CAISSE":
            besoins = self.db.query(Besoin).filter(
                Besoin.statut == StatutBesoin.COMPTABLE_VALIDE
            ).all()
        elif role.upper() == "DG":
            besoins = self.db.query(Besoin).filter(
                Besoin.statut == StatutBesoin.CAISSE_VALIDE
            ).all()
        else:
            besoins = self.db.query(Besoin).filter(
                Besoin.statut.in_([StatutBesoin.BROUILLON,
                                  StatutBesoin.EN_VALIDATION,
                                  StatutBesoin.COMPTABLE_VALIDE,
                                  StatutBesoin.CAISSE_VALIDE])
            ).all()

        return self._format_besoins_response(besoins)

    def _format_besoins_response(self, besoins: List[Besoin]) -> List[dict]:
        """Formate la réponse des besoins."""
        result = []
        for besoin in besoins:
            panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first() if besoin.id_panne else None
            bien = panne.bien if panne else None

            result.append({
                "id_besoin": besoin.id_besoin,
                "numero_demande": besoin.numero_demande,
                "montant_total": float(besoin.montant_total) if besoin.montant_total else 0,
                "date_creation": besoin.date_creation,
                "statut": besoin.statut.value if besoin.statut else None,
                "panne_description": panne.description if panne else None,
                "bien_designation": self._get_bien_designation(bien),
                "nombre_lignes": len(besoin.lignes) if besoin.lignes else 0,
                "validations": [
                    {
                        "ordre": v.ordre_validateur.value,
                        "decision": v.decision.value,
                        "date": v.date_validation,
                        "validateur": v.validateur.nom if v.validateur else None
                    }
                    for v in besoin.validations if v
                ]
            })
        return result

    def get_workflow_details(self, besoin_id: int) -> dict:
        """Récupère les détails du workflow d'un besoin."""
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
        if not besoin:
            raise ValueError("Besoin non trouvé")

        validations = self.db.query(Validation).filter(
            Validation.id_besoin == besoin_id
        ).order_by(Validation.date_validation).all()

        return self._build_workflow_response(besoin, validations)

    def _build_workflow_response(self, besoin: Besoin, validations: List[Validation]) -> dict:
        """
        Construit la réponse du workflow conforme au schéma ValidationWorkflowStatus.
        """
        # Créer les étapes avec leurs statuts
        etapes = []
        for ordre in [OrdreValidation.COMPTABLE, OrdreValidation.CAISSE, OrdreValidation.DG]:
            validation_existante = next((v for v in validations if v.ordre_validateur == ordre), None)
            
            if validation_existante:
                statut = "valide" if validation_existante.decision == DecisionValidation.APPROUVE else "rejete"
                decision = validation_existante.decision.value
                validateur = validation_existante.validateur.nom if validation_existante.validateur else None
                date_val = validation_existante.date_validation
                commentaire = validation_existante.commentaire
            else:
                statut = self._get_etape_statut(besoin, ordre)
                decision = None
                validateur = None
                date_val = None
                commentaire = None
            
            etapes.append({
                "ordre": ordre.value,
                "statut": statut,
                "decision": decision,
                "validateur": validateur,
                "date": date_val.isoformat() if date_val else None,
                "commentaire": commentaire
            })
        
        etape_actuelle = self._get_etape_actuelle(besoin)
        progression = self._calculer_progression(validations)
        est_termine = besoin.statut in [StatutBesoin.APPROUVEE, StatutBesoin.REJETE]
        est_approuve = besoin.statut == StatutBesoin.APPROUVEE
        
        validations_realisees = [
            {
                "ordre": v.ordre_validateur.value,
                "decision": v.decision.value,
                "validateur": v.validateur.nom if v.validateur else None,
                "date": v.date_validation.isoformat() if v.date_validation else None,
                "commentaire": v.commentaire,
                "motif_rejet": v.motif_rejet if v.decision == DecisionValidation.REJETE else None
            }
            for v in validations
        ]
        
        etapes_suivantes = self._get_etapes_suivantes(besoin, validations)
        
        # 🟢 Vérifications budget et trésorerie pour FicheValidation / WorkflowValidation
        from ..services.caisse_service import CaisseService
        caisse_service = CaisseService(self.db)
        tresorerie_info = caisse_service.verifier_tresorerie(float(besoin.montant_total or 0))
        
        centre_cout = self._get_centre_cout_besoin(besoin)
        budget_info = self.budget_service.verifier_disponibilite(
            centre_cout,
            datetime.utcnow().year,
            float(besoin.montant_total or 0)
        )

        return {
            "id_besoin": besoin.id_besoin,
            "numero_demande": besoin.numero_demande,
            "statut_actuel": besoin.statut.value if besoin.statut else None,
            "montant_total": float(besoin.montant_total) if besoin.montant_total else 0,
            "etape_actuelle": etape_actuelle,
            "progression": progression,
            "est_termine": est_termine,
            "est_approuve": est_approuve,
            "etapes": etapes,
            "validations": validations_realisees,
            "etapes_suivantes": etapes_suivantes,
            "validations_realisees": validations_realisees,
            "verification_budget": {
                "est_disponible": budget_info.est_disponible,
                "solde_disponible": budget_info.solde_disponible,
                "message": budget_info.message
            },
            "verification_tresorerie": {
                "est_suffisante": tresorerie_info["est_suffisante"],
                "solde_disponible": tresorerie_info["solde_disponible"],
                "message": tresorerie_info["message"]
            }
        }

    def _get_etape_statut(self, besoin: Besoin, ordre: OrdreValidation) -> str:
        """Détermine le statut d'une étape en fonction du statut du besoin."""
        validations_existantes = self.db.query(Validation).filter(
            Validation.id_besoin == besoin.id_besoin
        ).all()
        
        for v in validations_existantes:
            if v.ordre_validateur == ordre:
                return "valide" if v.decision == DecisionValidation.APPROUVE else "rejete"
        
        statut_actuel = besoin.statut
        if statut_actuel == StatutBesoin.APPROUVEE:
            return "valide"
        if statut_actuel == StatutBesoin.REJETE:
            return "rejete"
        
        # Ordre du workflow : COMPTABLE -> CAISSE -> DG
        if statut_actuel in [StatutBesoin.BROUILLON, StatutBesoin.EN_VALIDATION]:
            return "en_attente" if ordre == OrdreValidation.COMPTABLE else "bloque"
        
        if statut_actuel == StatutBesoin.COMPTABLE_VALIDE:
            if ordre == OrdreValidation.COMPTABLE:
                return "valide"
            elif ordre == OrdreValidation.CAISSE:
                return "en_attente"
            else:
                return "bloque"
        
        if statut_actuel in [StatutBesoin.CAISSE_VALIDE, StatutBesoin.ATTENTE_STOCK]:
            if ordre in [OrdreValidation.COMPTABLE, OrdreValidation.CAISSE]:
                return "valide"
            elif ordre == OrdreValidation.DG:
                return "en_attente"
        
        return "en_attente"

    def _get_etape_actuelle(self, besoin: Besoin) -> Optional[str]:
        """Détermine l'étape actuelle du workflow (COMPTABLE -> CAISSE -> DG)."""
        statut_actuel = besoin.statut
        if statut_actuel == StatutBesoin.APPROUVEE:
            return "TERMINE"
        if statut_actuel == StatutBesoin.REJETE:
            return "REJETE"
        
        if statut_actuel in [StatutBesoin.BROUILLON, StatutBesoin.EN_VALIDATION]:
            return "COMPTABLE"
        if statut_actuel == StatutBesoin.COMPTABLE_VALIDE:
            return "CAISSE"
        if statut_actuel in [StatutBesoin.CAISSE_VALIDE, StatutBesoin.ATTENTE_STOCK]:
            return "DG"
        
        return "TERMINE"

    def _calculer_progression(self, validations: List[Validation]) -> float:
        """Calcule la progression en pourcentage."""
        if not validations:
            return 0.0
        
        total_etapes = 3  # COMPTABLE, CAISSE, DG
        etapes_validees = sum(1 for v in validations if v.decision == DecisionValidation.APPROUVE)
        
        if any(v.decision == DecisionValidation.REJETE for v in validations):
            return 0.0
        
        return round((etapes_validees / total_etapes) * 100, 2)

    def _get_etapes_suivantes(self, besoin: Besoin, validations: List[Validation]) -> List[str]:
        """Détermine les prochaines étapes disponibles."""
        statut_actuel = besoin.statut
        if statut_actuel in [StatutBesoin.APPROUVEE, StatutBesoin.REJETE]:
            return []
        
        if statut_actuel in [StatutBesoin.BROUILLON, StatutBesoin.EN_VALIDATION]:
            return ["COMPTABLE"]
        elif statut_actuel == StatutBesoin.COMPTABLE_VALIDE:
            return ["CAISSE"]
        elif statut_actuel in [StatutBesoin.CAISSE_VALIDE, StatutBesoin.ATTENTE_STOCK]:
            return ["DG"]
        
        return []

    def get_historique_validations(self, besoin_id: int) -> List[dict]:
        """Récupère l'historique des validations d'un besoin."""
        validations = self.db.query(Validation).filter(
            Validation.id_besoin == besoin_id
        ).order_by(Validation.date_validation.desc()).all()

        return [
            {
                "id_validation": v.id_validation,
                "ordre": v.ordre_validateur.value,
                "decision": v.decision.value,
                "validateur": v.validateur.nom if v.validateur else None,
                "date": v.date_validation,
                "commentaire": v.commentaire,
                "motif_rejet": v.motif_rejet if v.decision == DecisionValidation.REJETE else None
            }
            for v in validations
        ]

    # ============================================================
    # MÉTHODES DE COMPATIBILITÉ (legacy)
    # ============================================================

    def valider(self, *args, **kwargs):
        """Méthode legacy de validation."""
        pass

# backend/app/services/validation_service.py

# Ajouter ces méthodes à la classe ValidationService

def get_amortissements_en_attente(self) -> List[dict]:
    """
    Récupère les amortissements en attente de validation.
    """
    from ..models.amortissement import Amortissement, StatutAmortissement
    
    amortissements = self.db.query(Amortissement).filter(
        Amortissement.statut == StatutAmortissement.EN_ATTENTE
    ).all()
    
    result = []
    for a in amortissements:
        bien = None
        if a.id_bien:
            bien = self.db.query(Bien).filter(Bien.id_bien == a.id_bien).first()
        
        designation = "Bien non spécifié"
        if bien:
            designation = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip()
            if not designation:
                designation = f"Bien #{bien.id_bien}"
        
        result.append({
            "id_amortissement": a.id_amortissement,
            "id_bien": a.id_bien,
            "bien_designation": designation,
            "exercice": a.exercice,
            "annuite_comptable": float(a.annuite_comptable) if a.annuite_comptable else 0,
            "date_debut": a.date_debut.isoformat() if a.date_debut else None,
            "date_fin": a.date_fin.isoformat() if a.date_fin else None,
            "statut": a.statut.value if a.statut else None,
            "date_creation": a.date_creation.isoformat() if a.date_creation else None
        })
    
    return result


def get_cessions_en_attente(self) -> List[dict]:
    """
    Récupère les cessions en attente de validation.
    """
    from ..models.cession import Cession, StatutCession
    
    cessions = self.db.query(Cession).filter(
        Cession.statut.in_([StatutCession.EN_ATTENTE_VALIDATION, StatutCession.EN_COURS])
    ).all()
    
    result = []
    for c in cessions:
        bien = None
        if c.id_bien:
            bien = self.db.query(Bien).filter(Bien.id_bien == c.id_bien).first()
        
        designation = "Bien non spécifié"
        if bien:
            designation = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip()
            if not designation:
                designation = f"Bien #{bien.id_bien}"
        
        # Déterminer l'étape actuelle
        etape = "DEMANDE"
        if c.date_validation_finale:
            etape = "TERMINE"
        elif c.date_validation_dg:
            etape = "CAISSE"
        elif c.date_validation_caissier:
            etape = "COMPTABLE"
        
        result.append({
            "id_cession": c.id_cession,
            "id_bien": c.id_bien,
            "bien_designation": designation,
            "prix_cession": float(c.prix_cession) if c.prix_cession else 0,
            "acheteur": c.acheteur,
            "date_demande": c.date_demande.isoformat() if c.date_demande else None,
            "statut": c.statut.value if c.statut else None,
            "etape_actuelle": etape
        })
    
    return result