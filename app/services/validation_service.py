from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from datetime import datetime
from sqlalchemy import func
from ..models.validation import Validation, OrdreValidation, DecisionValidation
from ..models.besoin import Besoin, StatutBesoin
from ..models.ligne_besoin import LigneBesoin
from ..models.panne import Panne, StatutPanne
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..services.notification_service import NotificationService
from ..models.notification import TypeNotificationEnum
from ..services.fourniture_service import FournitureService
from ..services.stock_service import StockService
from ..services.audit_service import AuditService

class ValidationService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
        self.fourniture_service = FournitureService(db)
        self.stock_service = StockService(db)
        self.audit_service = AuditService(db)

    def _get_utilisateurs_par_roles(self, *roles: str) -> List[Utilisateur]:
        roles_upper = [role.upper() for role in roles]
        return (
            self.db.query(Utilisateur)
            .join(Role)
            .filter(func.upper(Role.nom).in_(roles_upper))
            .all()
        )
    
    def get_besoins_en_attente(self, role: str) -> List[dict]:
        besoins = []
        
        if role == "DG":
            besoins = self.db.query(Besoin).filter(Besoin.statut == StatutBesoin.BROUILLON).all()
        elif role == "COMPTABLE":
            besoins = self.db.query(Besoin).filter(Besoin.statut == StatutBesoin.DG_VALIDE).all()
        elif role == "CAISSE":
            besoins = self.db.query(Besoin).filter(Besoin.statut == StatutBesoin.COMPTABLE_VALIDE).all()
        
        result = []
        for besoin in besoins:
            panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first()
            bien = panne.bien if panne else None
            
            result.append({
                "id_besoin": besoin.id_besoin,
                "numero_demande": besoin.numero_demande,
                "montant_total": besoin.montant_total,
                "date_creation": besoin.date_creation,
                "statut": besoin.statut.value,
                "observations": besoin.observations,
                "panne_description": panne.description if panne else None,
                "bien_designation": f"{getattr(bien, 'marque', None) or getattr(bien, 'fabricant', None) or ''} {getattr(bien, 'modele', '')}".strip() if bien else None,
                "nombre_lignes": len(besoin.lignes),
                "validations": [
                    {
                        "ordre": v.ordre_validateur.value,
                        "decision": v.decision.value,
                        "date": v.date_validation,
                        "validateur": v.validateur.nom if v.validateur else None
                    }
                    for v in besoin.validations
                ]
            })
        return result
    
    def valider_besoin(self, besoin_id: int, id_validateur: int, ordre_validateur: str, decision: str, commentaire: str = None) -> dict:
        besoin = (
            self.db.query(Besoin)
            .options(joinedload(Besoin.lignes).joinedload(LigneBesoin.piece))
            .filter(Besoin.id_besoin == besoin_id)
            .first()
        )
        if not besoin:
            raise ValueError("Besoin non trouvé")
        
        ordre_enum = OrdreValidation[ordre_validateur] if ordre_validateur in OrdreValidation.__members__ else None
        if not ordre_enum:
            raise ValueError(f"Ordre de validation invalide: {ordre_validateur}")
        
        if not besoin.peut_etre_validee(ordre_validateur):
            raise ValueError(f"Ce besoin n'est pas en attente de validation par {ordre_validateur} (Statut actuel: {besoin.statut.value})")
        
        decision_enum = DecisionValidation[decision] if decision in DecisionValidation.__members__ else None
        if not decision_enum:
            raise ValueError(f"Décision invalide: {decision}")
        
        validation = Validation(
            id_besoin=besoin_id,
            id_validateur=id_validateur,
            ordre_validateur=ordre_enum,
            decision=decision_enum,
            commentaire=commentaire,
            date_validation=datetime.utcnow()
        )
        self.db.add(validation)
        
        # Récupérer le technicien associé à la panne
        panne = self.db.query(Panne).filter(Panne.id_panne == besoin.id_panne).first()
        id_technicien = panne.id_technicien if panne else None
        
        if decision_enum == DecisionValidation.REJETE:
            besoin.statut = StatutBesoin.REJETE
            if panne:
                panne.statut = StatutPanne.DIAGNOSTIQUEE
            self.fourniture_service.annuler_fournitures_besoin(besoin_id)
            
            # 🆕 Notification de rejet au technicien
            if id_technicien:
                self.notification_service.envoyer_notification(
                    ids_destinataires=id_technicien,  # ✅ Correction: peut être un int
                    type_notif=TypeNotificationEnum.BESOIN_REJETE,
                    titre=f"❌ Besoin rejeté - {besoin.numero_demande}",
                    contenu=f"Votre demande {besoin.numero_demande} a été rejetée par {ordre_validateur}. Motif: {commentaire or 'Non spécifié'}",
                    lien=f"/pannes/{besoin.id_panne}"
                )
        else:
            if ordre_enum == OrdreValidation.CAISSE:
                ancien_statut = besoin.statut.value
                besoin.statut = StatutBesoin.APPROUVEE
                if panne:
                    panne.statut = StatutPanne.EN_COURS

                self.db.flush()

                stock_status = self.stock_service.evaluer_stock_besoin(besoin_id)
                pieces_manquantes = self.stock_service.get_pieces_manquantes(besoin_id)

                self.fourniture_service.creer_demandes_fourniture(besoin_id, commit=False)

                if stock_status in ("STOCK_INSUFFISANT", "STOCK_NUL"):
                    besoin.statut = StatutBesoin.ATTENTE_STOCK
                    lignes_manquantes = ", ".join(
                        f"{p['designation']} (manque {p['quantite_manquante']})"
                        for p in pieces_manquantes
                    )
                    priorite = panne.priorite.value if panne else "MOYENNE"
                    stock_titre = f"⚠️ Stock insuffisant - Besoin {besoin.numero_demande}"
                    stock_contenu = (
                        f"Le besoin {besoin.numero_demande} est approuvé mais bloqué. "
                        f"Priorité panne: {priorite}. Pièces manquantes: {lignes_manquantes}"
                    )
                    for gest in self._get_utilisateurs_par_roles("GESTIONNAIRE", "ADMIN"):
                        self.notification_service.envoyer_notification(
                            ids_destinataires=gest.id,
                            type_notif=TypeNotificationEnum.STOCK_INSUFFISANT,
                            titre=stock_titre,
                            contenu=stock_contenu,
                            lien="/besoins/attente-stock",
                        )
                    for mag in self._get_utilisateurs_par_roles("MAGASINIER"):
                        self.notification_service.envoyer_notification(
                            ids_destinataires=mag.id,
                            type_notif=TypeNotificationEnum.STOCK_INSUFFISANT,
                            titre=stock_titre,
                            contenu=(
                                f"{stock_contenu} "
                                "Veuillez traiter la demande de fourniture : livraison partielle ou refus."
                            ),
                            lien="/fournitures/en-attente",
                        )
                else:
                    besoin.statut = StatutBesoin.APPROUVEE

                lignes_desc = ", ".join(
                    f"{l.piece.designation} x{l.quantite}"
                    for l in besoin.lignes
                    if l.piece
                )
                for mag in self._get_utilisateurs_par_roles("MAGASINIER"):
                    if stock_status in ("STOCK_INSUFFISANT", "STOCK_NUL"):
                        contenu_mag = (
                            f"Le besoin {besoin.numero_demande} nécessite votre décision. "
                            f"Pièces demandées: {lignes_desc}. "
                            "Vous pouvez livrer partiellement ou refuser la fourniture."
                        )
                        titre_mag = f"📦 Fourniture à traiter (stock insuffisant) - {besoin.numero_demande}"
                    else:
                        contenu_mag = (
                            f"Un besoin a été approuvé. Veuillez préparer la fourniture "
                            f"des pièces suivantes : {lignes_desc}"
                        )
                        titre_mag = f"📦 Nouvelle demande de fourniture - Besoin {besoin.numero_demande}"

                    self.notification_service.envoyer_notification(
                        ids_destinataires=mag.id,
                        type_notif=TypeNotificationEnum.FOURNITURE_EN_ATTENTE,
                        titre=titre_mag,
                        contenu=contenu_mag,
                        lien="/fournitures/en-attente",
                    )

                self.audit_service.log_update(
                    user_id=id_validateur,
                    table_name="besoins",
                    record_id=besoin_id,
                    old_values={"statut": ancien_statut},
                    new_values={
                        "statut": besoin.statut.value,
                        "stock_status": stock_status,
                        "fournitures_creees": True,
                    },
                )

                if id_technicien:
                    message = (
                        "Les travaux peuvent commencer."
                        if besoin.statut == StatutBesoin.APPROUVEE
                        else "En attente de réapprovisionnement du stock."
                    )
                    self.notification_service.envoyer_notification(
                        ids_destinataires=id_technicien,
                        type_notif=TypeNotificationEnum.BESOIN_VALIDE,
                        titre=f"✅ Besoin approuvé - {besoin.numero_demande}",
                        contenu=f"Votre demande {besoin.numero_demande} a été approuvée. {message}",
                        lien=f"/pannes/{besoin.id_panne}",
                    )
            else:
                besoin.passer_validation_suivante()
                
                # 🆕 Notification au prochain validateur
                if besoin.statut == StatutBesoin.DG_VALIDE:
                    prochains_validateurs = self.db.query(Utilisateur).join(Role).filter(Role.nom == "COMPTABLE").all()
                    type_notif = TypeNotificationEnum.BESOIN_VALIDE
                    titre = f"📋 Besoin à valider - {besoin.numero_demande}"
                    contenu = f"La demande {besoin.numero_demande} est en attente de validation par le Comptable. Montant: {besoin.montant_total:,.0f} USD"
                elif besoin.statut == StatutBesoin.COMPTABLE_VALIDE:
                    prochains_validateurs = self.db.query(Utilisateur).join(Role).filter(Role.nom == "CAISSE").all()
                    type_notif = TypeNotificationEnum.BESOIN_VALIDE
                    titre = f"💰 Besoin à valider - {besoin.numero_demande}"
                    contenu = f"La demande {besoin.numero_demande} est en attente de validation par la Caisse pour libération des fonds."
                else:
                    prochains_validateurs = []
                
                for validateur in prochains_validateurs:
                    self.notification_service.envoyer_notification(
                        ids_destinataires=validateur.id,  # ✅ Correction: peut être un int
                        type_notif=type_notif,
                        titre=titre,
                        contenu=contenu,
                        lien=f"/validations/{besoin.id_besoin}"
                    )
        
        self.db.commit()
        self.db.refresh(besoin)

        return {
            "id_besoin": besoin.id_besoin,
            "numero_demande": besoin.numero_demande,
            "statut": besoin.statut.value,
            "montant_total": besoin.montant_total
        }
    
    def get_workflow_details(self, besoin_id: int) -> dict:
        besoin = self.db.query(Besoin).filter(Besoin.id_besoin == besoin_id).first()
        if not besoin:
            raise ValueError("Besoin non trouvé")
        
        validations = self.db.query(Validation).filter(
            Validation.id_besoin == besoin_id
        ).order_by(Validation.ordre_validateur).all()
        
        workflow = {
            "id_besoin": besoin.id_besoin,
            "numero_demande": besoin.numero_demande,
            "statut_actuel": besoin.statut.value,
            "montant_total": besoin.montant_total,
            "etapes": [
                {
                    "ordre": ordre.value,
                    "statut": "en_attente",
                    "decision": None,
                    "validateur": None,
                    "date": None,
                    "commentaire": None
                }
                for ordre in OrdreValidation
            ],
            "validations_realisees": [
                {
                    "ordre": v.ordre_validateur.value,
                    "decision": v.decision.value,
                    "validateur": v.validateur.nom if v.validateur else None,
                    "date": v.date_validation,
                    "commentaire": v.commentaire
                }
                for v in validations
            ]
        }
        
        for v in validations:
            for etape in workflow["etapes"]:
                if etape["ordre"] == v.ordre_validateur.value:
                    etape["statut"] = "valide" if v.decision == DecisionValidation.APPROUVE else "rejete"
                    etape["decision"] = v.decision.value
                    etape["validateur"] = v.validateur.nom if v.validateur else None
                    etape["date"] = v.date_validation
                    etape["commentaire"] = v.commentaire
                    break
        
        return workflow
    
    def get_historique_validations(self, besoin_id: int) -> List[dict]:
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
                "commentaire": v.commentaire
            }
            for v in validations
        ]