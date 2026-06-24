# backend/app/services/audit_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import json

from ..models.audit_log import AuditLog
from ..models.utilisateur import Utilisateur

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