# backend/app/services/audit_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import json

from ..models.audit_log import AuditLog
from ..models.utilisateur import Utilisateur
from ..models.bien import Bien
from ..models.journal_evenements_immobilisation import JournalEvenementImmobilisation, TypeEvenementImmobilisation

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        user_id: Optional[int],
        table_name: str,
        record_id: Optional[int],
        action: str,
        anciennes_valeurs: Optional[Dict[str, Any]] = None,
        nouvelles_valeurs: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """Enregistre une action dans le journal d'audit"""
        
        # Nettoyer les valeurs pour éviter les erreurs JSON
        if anciennes_valeurs:
            anciennes_valeurs = self._clean_json_values(anciennes_valeurs)
        if nouvelles_valeurs:
            nouvelles_valeurs = self._clean_json_values(nouvelles_valeurs)
        
        log = AuditLog(
            id_utilisateur=user_id,
            table_concernee=table_name,
            id_enregistrement=record_id,
            action=action,
            anciennes_valeurs=anciennes_valeurs,
            nouvelles_valeurs=nouvelles_valeurs,
            adresse_ip=ip_address,
            user_agent=user_agent
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        
        logger.info(f"Audit: {action} on {table_name}#{record_id} by user#{user_id}")
        return log

    def _clean_json_values(self, values: Dict) -> Dict:
        """Nettoie les valeurs pour le stockage JSON"""
        cleaned = {}
        for key, value in values.items():
            if value is None:
                cleaned[key] = None
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = value
            elif isinstance(value, datetime):
                cleaned[key] = value.isoformat()
            elif hasattr(value, 'value'):  # Pour les enums
                cleaned[key] = value.value
            else:
                try:
                    cleaned[key] = str(value)
                except:
                    cleaned[key] = None
        return cleaned

    def log_create(self, user_id: int, table_name: str, record_id: int, new_values: Dict, request=None):
        """Helper pour loguer une création"""
        ip = None
        ua = None
        if request:
            if hasattr(request, 'client') and request.client:
                ip = request.client.host
            if hasattr(request, 'headers'):
                ua = request.headers.get('user-agent')
        
        return self.log_action(
            user_id=user_id,
            table_name=table_name,
            record_id=record_id,
            action="CREATE",
            nouvelles_valeurs=new_values,
            ip_address=ip,
            user_agent=ua
        )

    def log_update(self, user_id: int, table_name: str, record_id: int, 
                   old_values: Dict, new_values: Dict, request=None):
        """Helper pour loguer une modification"""
        ip = None
        ua = None
        if request:
            if hasattr(request, 'client') and request.client:
                ip = request.client.host
            if hasattr(request, 'headers'):
                ua = request.headers.get('user-agent')
        
        return self.log_action(
            user_id=user_id,
            table_name=table_name,
            record_id=record_id,
            action="UPDATE",
            anciennes_valeurs=old_values,
            nouvelles_valeurs=new_values,
            ip_address=ip,
            user_agent=ua
        )

    def log_delete(self, user_id: int, table_name: str, record_id: int, old_values: Dict, request=None):
        """Helper pour loguer une suppression"""
        ip = None
        ua = None
        if request:
            if hasattr(request, 'client') and request.client:
                ip = request.client.host
            if hasattr(request, 'headers'):
                ua = request.headers.get('user-agent')
        
        return self.log_action(
            user_id=user_id,
            table_name=table_name,
            record_id=record_id,
            action="DELETE",
            anciennes_valeurs=old_values,
            ip_address=ip,
            user_agent=ua
        )

    def log_login(self, user_id: Optional[int], email: str, success: bool, request=None):
        """Helper pour loguer une tentative de connexion"""
        ip = None
        ua = None
        if request:
            if hasattr(request, 'client') and request.client:
                ip = request.client.host
            if hasattr(request, 'headers'):
                ua = request.headers.get('user-agent')
        
        return self.log_action(
            user_id=user_id,
            table_name="auth",
            record_id=None,
            action="LOGIN_SUCCESS" if success else "LOGIN_FAILED",
            nouvelles_valeurs={"email": email, "success": success},
            ip_address=ip,
            user_agent=ua
        )

    def log_logout(self, user_id: int, request=None):
        """Helper pour loguer une déconnexion"""
        ip = None
        ua = None
        if request:
            if hasattr(request, 'client') and request.client:
                ip = request.client.host
            if hasattr(request, 'headers'):
                ua = request.headers.get('user-agent')
        
        return self.log_action(
            user_id=user_id,
            table_name="auth",
            record_id=None,
            action="LOGOUT",
            ip_address=ip,
            user_agent=ua
        )

    def get_logs(
        self,
        utilisateur_id: Optional[int] = None,
        table: Optional[str] = None,
        action: Optional[str] = None,
        date_debut: Optional[datetime] = None,
        date_fin: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[List[AuditLog], int]:
        query = self.db.query(AuditLog)

        if utilisateur_id:
            query = query.filter(AuditLog.id_utilisateur == utilisateur_id)
        if table:
            query = query.filter(AuditLog.table_concernee == table)
        if action:
            query = query.filter(AuditLog.action == action)
        if date_debut:
            query = query.filter(AuditLog.date_action >= date_debut)
        if date_fin:
            query = query.filter(AuditLog.date_action <= date_fin)

        total = query.count()
        offset = (page - 1) * page_size
        items = query.order_by(AuditLog.date_action.desc()).offset(offset).limit(page_size).all()

        return items, total

    def get_user_history(self, user_id: int, limit: int = 100) -> List[AuditLog]:
        return self.db.query(AuditLog).filter(
            AuditLog.id_utilisateur == user_id
        ).order_by(AuditLog.date_action.desc()).limit(limit).all()

    def get_record_history(self, table_name: str, record_id: int, limit: int = 50) -> List[AuditLog]:
        return self.db.query(AuditLog).filter(
            AuditLog.table_concernee == table_name,
            AuditLog.id_enregistrement == record_id
        ).order_by(AuditLog.date_action.desc()).limit(limit).all()

    # ============================================================
    # MÉTHODES TÂCHE 2 - AUDIT SPÉCIFIQUE
    # ============================================================
    
    def log_validation(self, user_id: int, objet_type: str, objet_id: int,
                       decision: str, details: dict, request=None):
        """
        Journalise une action de validation.
        """
        return self.log_action(
            user_id=user_id,
            table_name=objet_type,
            record_id=objet_id,
            action=f"VALIDATION_{decision}",
            nouvelles_valeurs=details,
            request=request
        )

    def log_cession(self, user_id: int, bien_id: int, cession_id: int,
                    prix_vente: float, actif_remplacement_id: int = None, request=None):
        """
        Journalise une cession.
        """
        details = {
            "cession_id": cession_id,
            "prix_vente": prix_vente,
            "actif_remplacement_id": actif_remplacement_id
        }
        return self.log_action(
            user_id=user_id,
            table_name="biens",
            record_id=bien_id,
            action="CESSION",
            nouvelles_valeurs=details,
            request=request
        )

    def log_amortissement_validation(self, user_id: int, amortissement_id: int,
                                      decision: str, montant: float, request=None):
        """
        Journalise la validation d'un amortissement.
        """
        details = {
            "amortissement_id": amortissement_id,
            "decision": decision,
            "montant": montant
        }
        return self.log_action(
            user_id=user_id,
            table_name="amortissements",
            record_id=amortissement_id,
            action=f"AMORTISSEMENT_{decision}",
            nouvelles_valeurs=details,
            request=request
        )

    def log_ecriture_comptable(self, user_id: int, ecriture_id: int,
                                type_operation: str, montant: float, request=None):
        """
        Journalise la création d'une écriture comptable.
        """
        details = {
            "ecriture_id": ecriture_id,
            "type_operation": type_operation,
            "montant": montant
        }
        return self.log_action(
            user_id=user_id,
            table_name="ecritures_comptables",
            record_id=ecriture_id,
            action="ECRITURE_CREEE",
            nouvelles_valeurs=details,
            request=request
        )

    def log_workflow_etape(self, user_id: int, workflow_type: str,
                           objet_id: int, etape: str, action: str, request=None):
        """
        Journalise une étape de workflow.
        """
        details = {
            "workflow_type": workflow_type,
            "etape": etape,
            "action": action
        }
        return self.log_action(
            user_id=user_id,
            table_name=workflow_type,
            record_id=objet_id,
            action=f"WORKFLOW_{etape}_{action}",
            nouvelles_valeurs=details,
            request=request
        )

    def get_historique_validations(self, objet_type: str, objet_id: int) -> List[dict]:
        """
        Récupère l'historique des validations pour un objet.
        """
        logs = self.db.query(AuditLog).filter(
            AuditLog.table_concernee == objet_type,
            AuditLog.id_enregistrement == objet_id,
            AuditLog.action.like('VALIDATION_%')
        ).order_by(AuditLog.date_action.desc()).all()
        
        return [
            {
                "date": log.date_action.isoformat(),
                "action": log.action,
                "utilisateur": log.id_utilisateur,
                "anciennes_valeurs": log.anciennes_valeurs,
                "nouvelles_valeurs": log.nouvelles_valeurs,
                "ip": log.adresse_ip
            }
            for log in logs
        ]

    def get_historique_cessions(self, bien_id: int) -> List[dict]:
        """
        Récupère l'historique des cessions pour un bien.
        """
        logs = self.db.query(AuditLog).filter(
            AuditLog.table_concernee == "biens",
            AuditLog.id_enregistrement == bien_id,
            AuditLog.action == "CESSION"
        ).order_by(AuditLog.date_action.desc()).all()
        
        return [
            {
                "date": log.date_action.isoformat(),
                "utilisateur": log.id_utilisateur,
                "nouvelles_valeurs": log.nouvelles_valeurs,
                "ip": log.adresse_ip
            }
            for log in logs
        ]

    def get_historique_amortissements(self, bien_id: int) -> List[dict]:
        """
        Récupère l'historique des amortissements pour un bien.
        """
        logs = self.db.query(AuditLog).filter(
            AuditLog.table_concernee == "amortissements",
            AuditLog.id_enregistrement == bien_id,
            AuditLog.action.like('AMORTISSEMENT_%')
        ).order_by(AuditLog.date_action.desc()).all()
        
        return [
            {
                "date": log.date_action.isoformat(),
                "action": log.action,
                "utilisateur": log.id_utilisateur,
                "nouvelles_valeurs": log.nouvelles_valeurs,
                "ip": log.adresse_ip
            }
            for log in logs
        ]

    # ============================================================
    # NOUVELLES MÉTHODES TÂCHE 3
    # ============================================================

    def journaliser(
        self, 
        bien_id: int, 
        type_evenement: TypeEvenementImmobilisation, 
        libelle: str, 
        montant: float = 0.0, 
        reference_piece: str = None,
        ancienne_valeur: float = None,
        nouvelle_valeur: float = None,
        bien_remplace_id: int = None,
        bien_nouveau_id: int = None,
        utilisateur_id: int = None,
        metadonnees: str = None
    ) -> JournalEvenementImmobilisation:
        """
        Journalise un événement dans le journal des immobilisations
        """
        evenement = JournalEvenementImmobilisation(
            bien_id=bien_id,
            type_evenement=type_evenement,
            date_evenement=datetime.utcnow(),
            libelle=libelle,
            montant=montant,
            reference_piece=reference_piece,
            ancienne_valeur=ancienne_valeur,
            nouvelle_valeur=nouvelle_valeur,
            bien_remplace_id=bien_remplace_id,
            bien_nouveau_id=bien_nouveau_id,
            utilisateur_id=utilisateur_id,
            metadonnees=metadonnees
        )
        
        self.db.add(evenement)
        self.db.commit()
        self.db.refresh(evenement)
        
        # Journaliser également dans l'audit log
        self.log_action(
            user_id=utilisateur_id,
            table_name="journal_evenements_immobilisation",
            record_id=evenement.id,
            action=f"JOURNAL_{type_evenement.value}",
            nouvelles_valeurs={
                "bien_id": bien_id,
                "libelle": libelle,
                "montant": montant
            }
        )
        
        logger.info(f"Journal immobilisation: {type_evenement.value} - {libelle} (Bien #{bien_id})")
        
        return evenement
    
    def get_historique_bien(self, bien_id: int, limite: int = 100) -> List[JournalEvenementImmobilisation]:
        """
        Récupère tout l'historique d'un bien
        """
        return self.db.query(JournalEvenementImmobilisation).filter(
            JournalEvenementImmobilisation.bien_id == bien_id
        ).order_by(JournalEvenementImmobilisation.date_evenement.desc()).limit(limite).all()
    
    def get_historique_bien_chronologique(self, bien_id: int) -> List[JournalEvenementImmobilisation]:
        """
        Récupère l'historique d'un bien dans l'ordre chronologique
        """
        return self.db.query(JournalEvenementImmobilisation).filter(
            JournalEvenementImmobilisation.bien_id == bien_id
        ).order_by(JournalEvenementImmobilisation.date_evenement.asc()).all()
    
    def get_arbre_remplacement(self, bien_id: int) -> List[dict]:
        """
        Récupère l'arbre complet de remplacement d'un bien
        (Bien original → Bien de remplacement → Bien suivant...)
        """
        historique = []
        current_bien_id = bien_id
        
        # Récupérer le bien actuel
        bien_actuel = self.db.query(Bien).filter(Bien.id_bien == current_bien_id).first()
        if not bien_actuel:
            return historique
        
        # Ajouter le bien de départ
        historique.append({
            "type": "original",
            "bien_id": current_bien_id,
            "bien_nom": self._get_bien_designation(bien_actuel),
            "date": bien_actuel.date_acquisition if bien_actuel.date_acquisition else None
        })
        
        # Parcourir les remplacements
        while current_bien_id:
            # Trouver l'événement de sortie où ce bien a été remplacé
            event = self.db.query(JournalEvenementImmobilisation).filter(
                JournalEvenementImmobilisation.bien_remplace_id == current_bien_id,
                JournalEvenementImmobilisation.type_evenement.in_([
                    TypeEvenementImmobilisation.SORTIE_CESSION,
                    TypeEvenementImmobilisation.SORTIE_REBUT,
                    TypeEvenementImmobilisation.REMPLACEMENT
                ])
            ).first()
            
            if event and event.bien_nouveau_id:
                nouveau_bien = self.db.query(Bien).filter(
                    Bien.id_bien == event.bien_nouveau_id
                ).first()
                
                if nouveau_bien:
                    historique.append({
                        "type": "remplacement",
                        "ancien_bien_id": current_bien_id,
                        "nouveau_bien_id": event.bien_nouveau_id,
                        "bien_nom": self._get_bien_designation(nouveau_bien),
                        "date": event.date_evenement,
                        "motif": event.libelle,
                        "montant": event.montant
                    })
                    current_bien_id = event.bien_nouveau_id
                else:
                    break
            else:
                break
        
        return historique
    
    def get_arbre_remplacement_inverse(self, bien_id: int) -> List[dict]:
        """
        Récupère l'arbre de remplacement inverse d'un bien
        (Bien actuel → Bien qui l'a remplacé → ...)
        """
        historique = []
        current_bien_id = bien_id
        
        while current_bien_id:
            # Trouver l'événement où ce bien a été remplacé par un autre
            event = self.db.query(JournalEvenementImmobilisation).filter(
                JournalEvenementImmobilisation.bien_nouveau_id == current_bien_id,
                JournalEvenementImmobilisation.type_evenement.in_([
                    TypeEvenementImmobilisation.SORTIE_CESSION,
                    TypeEvenementImmobilisation.SORTIE_REBUT,
                    TypeEvenementImmobilisation.REMPLACEMENT
                ])
            ).first()
            
            if event and event.bien_remplace_id:
                ancien_bien = self.db.query(Bien).filter(
                    Bien.id_bien == event.bien_remplace_id
                ).first()
                
                if ancien_bien:
                    historique.append({
                        "type": "remplace_par",
                        "ancien_bien_id": event.bien_remplace_id,
                        "nouveau_bien_id": current_bien_id,
                        "bien_nom": self._get_bien_designation(ancien_bien),
                        "date": event.date_evenement,
                        "motif": event.libelle
                    })
                    current_bien_id = event.bien_remplace_id
                else:
                    break
            else:
                break
        
        return historique
    
    def get_evenements_par_type(self, type_evenement: TypeEvenementImmobilisation, 
                                date_debut: Optional[datetime] = None,
                                date_fin: Optional[datetime] = None,
                                limit: int = 100) -> List[JournalEvenementImmobilisation]:
        """
        Récupère les événements par type
        """
        query = self.db.query(JournalEvenementImmobilisation).filter(
            JournalEvenementImmobilisation.type_evenement == type_evenement
        )
        
        if date_debut:
            query = query.filter(JournalEvenementImmobilisation.date_evenement >= date_debut)
        if date_fin:
            query = query.filter(JournalEvenementImmobilisation.date_evenement <= date_fin)
        
        return query.order_by(JournalEvenementImmobilisation.date_evenement.desc()).limit(limit).all()
    
    def get_statistiques_journal(self, date_debut: Optional[datetime] = None,
                                 date_fin: Optional[datetime] = None) -> dict:
        """
        Récupère les statistiques du journal des immobilisations
        """
        query = self.db.query(JournalEvenementImmobilisation)
        
        if date_debut:
            query = query.filter(JournalEvenementImmobilisation.date_evenement >= date_debut)
        if date_fin:
            query = query.filter(JournalEvenementImmobilisation.date_evenement <= date_fin)
        
        # Nombre total d'événements
        total = query.count()
        
        # Répartition par type
        repartition_par_type = {}
        for type_event in TypeEvenementImmobilisation:
            count = query.filter(
                JournalEvenementImmobilisation.type_evenement == type_event
            ).count()
            if count > 0:
                repartition_par_type[type_event.value] = count
        
        # Montant total des événements
        montant_total = query.with_entities(
            func.coalesce(func.sum(JournalEvenementImmobilisation.montant), 0)
        ).scalar() or 0
        
        # Biens concernés
        biens_conernes = query.with_entities(
            func.count(func.distinct(JournalEvenementImmobilisation.bien_id))
        ).scalar() or 0
        
        return {
            "total_evenements": total,
            "repartition_par_type": repartition_par_type,
            "montant_total": round(float(montant_total), 2),
            "biens_conernes": biens_conernes,
            "periode": {
                "debut": date_debut.isoformat() if date_debut else None,
                "fin": date_fin.isoformat() if date_fin else None
            }
        }
    
    def verifier_chainage_remplacement(self, bien_id: int) -> dict:
        """
        Vérifie si un bien a une chaîne de remplacement valide
        """
        arbre = self.get_arbre_remplacement(bien_id)
        
        return {
            "bien_id": bien_id,
            "a_remplacement": len(arbre) > 1,
            "nombre_remplacements": len(arbre) - 1 if len(arbre) > 1 else 0,
            "arbre": arbre,
            "est_valide": self._verifier_chainage_continu(arbre)
        }
    
    def _get_bien_designation(self, bien: Bien) -> str:
        """Récupère la désignation d'un bien"""
        if hasattr(bien, 'marque') and hasattr(bien, 'modele'):
            return f"{bien.marque or ''} {bien.modele or ''}".strip() or f"Bien #{bien.id_bien}"
        return bien.description or f"Bien #{bien.id_bien}"
    
    def _verifier_chainage_continu(self, arbre: List[dict]) -> bool:
        """Vérifie que la chaîne de remplacement est continue"""
        if len(arbre) <= 1:
            return True
        
        for i in range(len(arbre) - 1):
            if arbre[i].get('bien_id') != arbre[i + 1].get('ancien_bien_id'):
                return False
        
        return True