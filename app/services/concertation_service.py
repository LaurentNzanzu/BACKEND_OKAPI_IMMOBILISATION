# app/services/concertation_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging

from ..models.discussion_concertation import (
    DiscussionConcertation, MessageConcertation, ValidationConcertation,
    TypeValidationEnum, DecisionValidationConcertation
)
from ..models.bien import Bien
from ..models.panne import Panne
from ..models.maintenance import Maintenance
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..models.notification import TypeNotificationEnum
from ..services.notification_service import NotificationService
from ..schemas.concertation import (
    DiscussionConcertationCreate,
    MessageConcertationCreate,
    ValidationConcertationCreate
)

logger = logging.getLogger(__name__)

class ConcertationService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    def _calculer_vnc(self, bien: Bien) -> float:
        if not bien:
            return 0.0
        brut = float(bien.prix_acquisition or 0)
        cumul_amo = float(bien.cumul_amortissement or 0)
        cumul_dep = float(bien.cumul_depreciation or 0)
        return round(max(0, brut - cumul_amo - cumul_dep), 2)

    def _get_bien_designation(self, bien: Bien) -> str:
        if not bien:
            return "Bien inconnu"
        if hasattr(bien, 'marque') and bien.marque:
            return f"{bien.marque} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
        if hasattr(bien, 'fabricant') and bien.fabricant:
            return f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
        return f"Bien #{bien.id_bien}"

    # app/services/concertation_service.py

    def detecter_biens_eligibles(self) -> List[Dict]:
        from datetime import datetime, timedelta
        
        resultats = []
        biens = self.db.query(Bien).filter(
            Bien.statut_comptable.in_(['ACTIF', 'EN_AMORTISSEMENT'])
        ).all()
        
        # Mots-clés indiquant un bien irrécupérable (pannes + maintenances)
        # Couvre : "irrécupérable", "irrecuperable", "non recuperable",
        #          "plus recuperable", "non récupérable", "hors d'usage", etc.
        MOTS_IRRECUP = [
            "irrécupérable",
            "irrecuperable",
            "non récupérable",
            "non recuperable",
            "plus récupérable",
            "plus recuperable",
            "n'est plus recuperable",
            "n'est plus récupérable",
            "hors d'usage",
            "hors usage",
            "irreparable",
            "irréparable",
        ]

        for bien in biens:
            date_limite = datetime.utcnow() - timedelta(days=365)

            pannes = self.db.query(Panne).filter(
                Panne.id_bien == bien.id_bien,
                Panne.date_declaration >= date_limite
            ).all()

            nb_pannes = len(pannes)

            # --- Correction #1 : utiliser le coût réel (MO + pièces) comme fallback
            # cout_total_reparation n'est mis à jour qu'à la clôture formelle de la panne.
            # Si la panne est encore ouverte, on calcule dynamiquement.
            def _cout_effectif(p: Panne) -> float:
                stored = float(p.cout_total_reparation or 0)
                if stored > 0:
                    return stored
                return float(p.cout_main_oeuvre or 0) + float(p.cout_pieces or 0)

            cout_maintenance = sum(_cout_effectif(p) for p in pannes)

            # --- Correction #2 : élargissement des mots-clés irrécupérable
            def _est_irrecup(texte: str) -> bool:
                t = (texte or "").lower()
                return any(mot in t for mot in MOTS_IRRECUP)

            panne_irrecup = any(
                _est_irrecup(p.diagnostic) or _est_irrecup(p.description)
                for p in pannes
            )

            maintenances_irrecup = self.db.query(Maintenance).filter(
                Maintenance.id_bien == bien.id_bien,
                or_(*[
                    Maintenance.rapport.ilike(f"%{mot}%")
                    for mot in MOTS_IRRECUP
                ])
            ).all()

            diagnostic_irrecup = panne_irrecup or len(maintenances_irrecup) > 0

            vnc = self._calculer_vnc(bien)
            prix_acquisition = float(bien.prix_acquisition or 0)
            ratio_vnc = vnc / prix_acquisition if prix_acquisition > 0 else 0

            condition_cession = (
                nb_pannes > 3 or
                cout_maintenance > prix_acquisition * 0.7 or
                ratio_vnc < 0.2
            )

            condition_rebut = diagnostic_irrecup or (cout_maintenance > prix_acquisition * 0.9)
            
            if condition_cession or condition_rebut:
                resultats.append({
                    "id_bien": bien.id_bien,
                    "designation": self._get_bien_designation(bien),
                    "prix_acquisition": prix_acquisition,
                    "cout_maintenance": cout_maintenance,
                    "nb_pannes": nb_pannes,
                    "vnc": vnc,
                    "ratio_vnc": ratio_vnc,
                    "diagnostic_irrecuperable": diagnostic_irrecup,
                    "type_recommande": "REBUT" if condition_rebut else "CESSION",
                    "motif": self._generer_motif(bien, nb_pannes, cout_maintenance, ratio_vnc, diagnostic_irrecup)
                })
        
        return resultats

    def creer_discussions_automatiques(self) -> Dict:
        """
        Détecte les biens éligibles et crée automatiquement une discussion
        de concertation pour chacun qui n'en a pas déjà une active.

        Retourne un résumé : créées, ignorées (doublons), erreurs.
        """
        from ..schemas.concertation import DiscussionConcertationCreate

        # Trouver un créateur système (DG en priorité, sinon COMPTABLE)
        createur = (
            self.db.query(Utilisateur)
            .join(Role)
            .filter(Role.nom.ilike("DG"), Utilisateur.est_actif == True)
            .first()
        )
        if not createur:
            createur = (
                self.db.query(Utilisateur)
                .join(Role)
                .filter(Role.nom.ilike("COMPTABLE"), Utilisateur.est_actif == True)
                .first()
            )
        if not createur:
            logger.error("creer_discussions_automatiques: aucun utilisateur DG/COMPTABLE actif trouvé")
            return {"creees": 0, "ignorees": 0, "erreurs": 0,
                    "detail": "Aucun utilisateur DG ou COMPTABLE actif disponible"}

        eligibles = self.detecter_biens_eligibles()
        creees, ignorees, erreurs = 0, 0, 0
        log_detail = []

        for bien_info in eligibles:
            id_bien = bien_info["id_bien"]
            type_val = bien_info["type_recommande"]   # "REBUT" ou "CESSION"
            designation = bien_info["designation"]
            motif = bien_info["motif"]

            # Vérifier si une discussion active existe déjà
            existante = self.db.query(DiscussionConcertation).filter(
                DiscussionConcertation.id_bien == id_bien,
                DiscussionConcertation.type_validation == type_val,
                DiscussionConcertation.est_active == True
            ).first()

            if existante:
                ignorees += 1
                log_detail.append({
                    "id_bien": id_bien,
                    "statut": "ignoree",
                    "raison": f"Discussion active #{existante.id} déjà existante"
                })
                continue

            try:
                data = DiscussionConcertationCreate(
                    id_bien=id_bien,
                    type_validation=type_val,
                    titre=(
                        f"[AUTO] {type_val} recommandée – {designation} | {motif[:80]}"
                    )
                )
                discussion = self.creer_discussion(data, createur.id)
                creees += 1
                log_detail.append({
                    "id_bien": id_bien,
                    "statut": "creee",
                    "id_discussion": discussion.id,
                    "type": type_val
                })
                logger.info(
                    f"Discussion #{discussion.id} créée automatiquement pour bien "
                    f"#{id_bien} ({type_val}) – {motif}"
                )
            except Exception as exc:
                erreurs += 1
                log_detail.append({
                    "id_bien": id_bien,
                    "statut": "erreur",
                    "raison": str(exc)
                })
                logger.warning(
                    f"Erreur création discussion auto pour bien #{id_bien}: {exc}"
                )

        return {
            "creees": creees,
            "ignorees": ignorees,
            "erreurs": erreurs,
            "total_eligibles": len(eligibles),
            "detail": log_detail
        }

    def _generer_motif(self, bien: Bien, nb_pannes: int, cout_maintenance: float,
                       ratio_vnc: float, diagnostic_irrecup: bool) -> str:
        # Cast en float pour éviter TypeError: Decimal * float
        prix = float(bien.prix_acquisition or 0)
        motifs = []
        if diagnostic_irrecup:
            motifs.append("Diagnostic technique irrécupérable")
        if nb_pannes > 3:
            motifs.append(f"{nb_pannes} pannes dans les 12 derniers mois")
        if cout_maintenance > prix * 0.7:
            motifs.append(f"Coût maintenance ({cout_maintenance:.0f} USD) > 70% de la valeur")
        if ratio_vnc < 0.2:
            motifs.append(f"VNC ({ratio_vnc*100:.0f}%) < 20% de la valeur d'origine")
        return " - ".join(motifs) if motifs else "Recommandation système"

    def creer_discussion(self, data: DiscussionConcertationCreate, id_createur: int) -> DiscussionConcertation:
        bien = self.db.query(Bien).filter(Bien.id_bien == data.id_bien).first()
        if not bien:
            raise ValueError(f"Bien {data.id_bien} non trouvé")

        existante = self.db.query(DiscussionConcertation).filter(
            DiscussionConcertation.id_bien == data.id_bien,
            DiscussionConcertation.type_validation == data.type_validation,
            DiscussionConcertation.est_active == True
        ).first()

        if existante:
            raise ValueError(f"Une discussion active existe déjà pour ce bien et ce type de validation")

        discussion = DiscussionConcertation(
            id_bien=data.id_bien,
            type_validation=data.type_validation,
            titre=data.titre,
            est_active=True,
            date_creation=datetime.utcnow()
        )
        self.db.add(discussion)
        self.db.flush()

        message = MessageConcertation(
            id_discussion=discussion.id,
            id_utilisateur=id_createur,
            contenu=f"🔔 Discussion ouverte pour la validation de {data.type_validation.value} du bien.",
            date_creation=datetime.utcnow()
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(discussion)

        self._notifier_nouvelle_discussion(discussion, id_createur)

        return discussion

    def get_discussion(self, id_discussion: int) -> Optional[DiscussionConcertation]:
        return self.db.query(DiscussionConcertation).options(
            joinedload(DiscussionConcertation.messages),
            joinedload(DiscussionConcertation.validations)
        ).filter(DiscussionConcertation.id == id_discussion).first()

    def get_discussions_by_bien(self, id_bien: int, type_validation: Optional[str] = None) -> List[DiscussionConcertation]:
        query = self.db.query(DiscussionConcertation).filter(
            DiscussionConcertation.id_bien == id_bien
        )
        if type_validation:
            query = query.filter(DiscussionConcertation.type_validation == type_validation)
        return query.order_by(DiscussionConcertation.date_creation.desc()).all()

    def get_discussions_en_attente(self) -> List[DiscussionConcertation]:
        return self.db.query(DiscussionConcertation).filter(
            DiscussionConcertation.est_active == True
        ).all()

    def cloturer_discussion(self, id_discussion: int) -> DiscussionConcertation:
        discussion = self.get_discussion(id_discussion)
        if not discussion:
            raise ValueError("Discussion non trouvée")

        discussion.est_active = False
        discussion.date_cloture = datetime.utcnow()
        self.db.commit()
        self.db.refresh(discussion)

        return discussion

    def ajouter_message(self, id_discussion: int, data: MessageConcertationCreate, id_utilisateur: int) -> MessageConcertation:
        discussion = self.get_discussion(id_discussion)
        if not discussion:
            raise ValueError("Discussion non trouvée")

        if not discussion.est_active:
            raise ValueError("Cette discussion est clôturée")

        if data.parent_id:
            parent = self.db.query(MessageConcertation).filter(
                MessageConcertation.id == data.parent_id,
                MessageConcertation.id_discussion == id_discussion
            ).first()
            if not parent:
                raise ValueError("Message parent non trouvé")

        message = MessageConcertation(
            id_discussion=id_discussion,
            id_utilisateur=id_utilisateur,
            contenu=data.contenu,
            parent_id=data.parent_id,
            date_creation=datetime.utcnow()
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        self._notifier_nouveau_message(discussion, message, id_utilisateur)

        return message

    def modifier_message(self, id_message: int, nouveau_contenu: str, id_utilisateur: int) -> MessageConcertation:
        message = self.db.query(MessageConcertation).filter(
            MessageConcertation.id == id_message,
            MessageConcertation.id_utilisateur == id_utilisateur
        ).first()

        if not message:
            raise ValueError("Message non trouvé ou non autorisé")

        discussion = self.get_discussion(message.id_discussion)
        if not discussion.est_active:
            raise ValueError("Cette discussion est clôturée")

        message.contenu = nouveau_contenu
        message.est_modifie = True
        message.date_modification = datetime.utcnow()
        self.db.commit()
        self.db.refresh(message)

        return message

    def enregistrer_validation(self, id_discussion: int, data: ValidationConcertationCreate, id_validateur: int) -> ValidationConcertation:
        discussion = self.get_discussion(id_discussion)
        if not discussion:
            raise ValueError("Discussion non trouvée")

        if not discussion.est_active:
            raise ValueError("Cette discussion est clôturée")

        validateur = self.db.query(Utilisateur).filter(Utilisateur.id == id_validateur).first()
        if not validateur or not validateur.role:
            raise ValueError("Utilisateur non trouvé ou sans rôle")

        role = validateur.role.nom.upper()
        if role not in ["DG", "COMPTABLE"]:
            raise ValueError(f"Seuls le DG et le Comptable peuvent valider. Rôle actuel: {role}")

        existante = self.db.query(ValidationConcertation).filter(
            ValidationConcertation.id_discussion == id_discussion,
            ValidationConcertation.id_validateur == id_validateur
        ).first()

        if existante:
            raise ValueError("Vous avez déjà validé cette discussion")

        validation = ValidationConcertation(
            id_discussion=id_discussion,
            id_validateur=id_validateur,
            decision=data.decision,
            commentaire=data.commentaire,
            date_decision=datetime.utcnow()
        )
        self.db.add(validation)
        self.db.commit()
        self.db.refresh(validation)

        statut = self.get_statut_discussion(id_discussion)

        if statut["est_valide"]:
            self._notifier_validation_complete(discussion, statut)
            self.cloturer_discussion(id_discussion)

        self._notifier_nouvelle_validation(discussion, validation, id_validateur)

        return validation

    def get_statut_discussion(self, id_discussion: int) -> Dict:
        validations = self.db.query(ValidationConcertation).filter(
            ValidationConcertation.id_discussion == id_discussion
        ).all()

        validation_dg = False
        validation_comptable = False
        date_dg = None
        date_comptable = None

        for v in validations:
            validateur = self.db.query(Utilisateur).filter(Utilisateur.id == v.id_validateur).first()
            if validateur and validateur.role and validateur.role.nom.upper() == "DG":
                validation_dg = v.decision == DecisionValidationConcertation.APPROUVE
                date_dg = v.date_decision
            elif validateur and validateur.role and validateur.role.nom.upper() == "COMPTABLE":
                validation_comptable = v.decision == DecisionValidationConcertation.APPROUVE
                date_comptable = v.date_decision

        est_valide = validation_dg and validation_comptable

        statut_global = "EN_ATTENTE"
        if est_valide:
            statut_global = "APPROUVE"
        elif validation_dg and not validation_comptable:
            statut_global = "DG_OK"
        elif validation_comptable and not validation_dg:
            statut_global = "COMPTABLE_OK"
        elif any(v.decision == DecisionValidationConcertation.REJETE for v in validations):
            statut_global = "REJETE"

        return {
            "validation_dg": validation_dg,
            "validation_comptable": validation_comptable,
            "date_validation_dg": date_dg,
            "date_validation_comptable": date_comptable,
            "est_valide": est_valide,
            "statut_global": statut_global
        }

    def verifier_eligibilite_action(self, id_bien: int, type_validation: str) -> Dict:
        discussion = self.db.query(DiscussionConcertation).filter(
            DiscussionConcertation.id_bien == id_bien,
            DiscussionConcertation.type_validation == type_validation,
            DiscussionConcertation.est_active == False
        ).order_by(DiscussionConcertation.date_creation.desc()).first()

        if not discussion:
            return {
                "eligible": False,
                "raison": "Aucune discussion de validation complétée",
                "validation_dg": False,
                "validation_comptable": False
            }

        statut = self.get_statut_discussion(discussion.id)

        return {
            "eligible": statut["est_valide"],
            "raison": "Validation double obtenue" if statut["est_valide"] else "Validation double en attente",
            "validation_dg": statut["validation_dg"],
            "validation_comptable": statut["validation_comptable"],
            "id_discussion": discussion.id
        }

    def _notifier_nouvelle_discussion(self, discussion: DiscussionConcertation, id_createur: int):
        bien = self.db.query(Bien).filter(Bien.id_bien == discussion.id_bien).first()
        designation = self._get_bien_designation(bien)

        validateurs = self.db.query(Utilisateur).join(Role).filter(
            Role.nom.in_(["DG", "COMPTABLE"])
        ).all()

        for validateur in validateurs:
            if validateur.id == id_createur:
                continue
            self.notification_service.envoyer_notification(
                ids_destinataires=validateur.id,
                type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                titre=f"💬 Nouvelle discussion de validation - {designation}",
                contenu=f"Une discussion pour la validation {discussion.type_validation.value} a été ouverte pour le bien {designation}.",
                lien=f"/biens/{discussion.id_bien}"
            )

    def _notifier_nouveau_message(self, discussion: DiscussionConcertation, message: MessageConcertation, id_auteur: int):
        bien = self.db.query(Bien).filter(Bien.id_bien == discussion.id_bien).first()
        designation = self._get_bien_designation(bien)

        participants = self.db.query(Utilisateur).join(Role).filter(
            Role.nom.in_(["DG", "COMPTABLE"])
        ).all()

        for participant in participants:
            if participant.id == id_auteur:
                continue
            self.notification_service.envoyer_notification(
                ids_destinataires=participant.id,
                type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                titre=f"💬 Nouveau message - {discussion.titre}",
                contenu=f"Un nouveau message a été ajouté dans la discussion pour le bien {designation}.",
                lien=f"/biens/{discussion.id_bien}"
            )

    def _notifier_nouvelle_validation(self, discussion: DiscussionConcertation, validation: ValidationConcertation, id_validateur: int):
        bien = self.db.query(Bien).filter(Bien.id_bien == discussion.id_bien).first()
        designation = self._get_bien_designation(bien)

        validateur = self.db.query(Utilisateur).filter(Utilisateur.id == id_validateur).first()
        role = validateur.role.nom.upper() if validateur.role else "UNKNOWN"

        autre_validateur = self.db.query(Utilisateur).join(Role).filter(
            Role.nom.in_(["DG", "COMPTABLE"]),
            Utilisateur.id != id_validateur
        ).first()

        if autre_validateur:
            decision_label = "APPROUVÉ" if validation.decision == DecisionValidationConcertation.APPROUVE else "REJETÉ"
            self.notification_service.envoyer_notification(
                ids_destinataires=autre_validateur.id,
                type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                titre=f"📋 Validation {decision_label} - {discussion.titre}",
                contenu=f"Le {role} a {decision_label} la validation pour le bien {designation}.",
                lien=f"/biens/{discussion.id_bien}"
            )

    def _notifier_validation_complete(self, discussion: DiscussionConcertation, statut: Dict):
        bien = self.db.query(Bien).filter(Bien.id_bien == discussion.id_bien).first()
        designation = self._get_bien_designation(bien)

        validateurs = self.db.query(Utilisateur).join(Role).filter(
            Role.nom.in_(["DG", "COMPTABLE"])
        ).all()

        for validateur in validateurs:
            self.notification_service.envoyer_notification(
                ids_destinataires=validateur.id,
                type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                titre=f"✅ Validation double complète - {designation}",
                contenu=f"La validation double pour la {discussion.type_validation.value} du bien {designation} est complète. L'action est maintenant disponible.",
                lien=f"/biens/{discussion.id_bien}"
            )