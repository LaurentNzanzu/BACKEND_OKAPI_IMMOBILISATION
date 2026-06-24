# backend/app/utils/audit_decorator.py
from functools import wraps
from fastapi import Request, Depends
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..services.audit_service import AuditService
from ..core.security import get_current_user
from ..models.utilisateur import Utilisateur

def audit_log(table_name: str, get_record_id=None):
    """
    Décorateur pour enregistrer automatiquement les actions dans l'audit.
    
    Args:
        table_name: Nom de la table concernée
        get_record_id: Fonction pour extraire l'ID de l'enregistrement depuis les args/kwargs
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extraire les éléments FastAPI
            request = None
            db = None
            current_user = None
            
            # Chercher les dépendances dans les kwargs
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value
                elif isinstance(value, Session):
                    db = value
                elif isinstance(value, Utilisateur):
                    current_user = value
            
            # Si pas de db, essayer de l'obtenir
            if not db:
                for arg in args:
                    if isinstance(arg, Session):
                        db = arg
                        break
            
            # Récupérer les anciennes valeurs si c'est une UPDATE
            anciennes_valeurs = None
            record_id = None
            
            if get_record_id:
                record_id = get_record_id(*args, **kwargs)
            
            # Si c'est une UPDATE, récupérer les anciennes valeurs
            action = kwargs.get('action', func.__name__.upper())
            if action == 'UPDATE' and record_id and db and table_name:
                anciennes_valeurs = get_old_values(db, table_name, record_id)
            
            # Exécuter la fonction originale
            result = await func(*args, **kwargs)
            
            # Enregistrer l'audit après l'opération
            if db and current_user and action in ['CREATE', 'UPDATE', 'DELETE']:
                audit_service = AuditService(db)
                
                nouvelles_valeurs = None
                if action == 'CREATE' and result:
                    nouvelles_valeurs = get_values_from_object(result)
                
                # Adresse IP et User Agent
                ip_address = None
                user_agent = None
                if request:
                    ip_address = request.client.host if request.client else None
                    user_agent = request.headers.get('user-agent')
                
                audit_service.log_action(
                    user_id=current_user.id,
                    table_name=table_name,
                    record_id=record_id,
                    action=action,
                    anciennes_valeurs=anciennes_valeurs,
                    nouvelles_valeurs=nouvelles_valeurs,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
            
            return result
        return wrapper
    return decorator

def get_old_values(db: Session, table_name: str, record_id: int):
    """Récupère les anciennes valeurs d'un enregistrement"""
    try:
        # Importer dynamiquement le modèle
        model = get_model_by_table_name(table_name)
        if model:
            record = db.query(model).filter(model.id == record_id).first()
            if record:
                return get_values_from_object(record)
    except Exception as e:
        print(f"Erreur récupération anciennes valeurs: {e}")
    return None

def get_values_from_object(obj):
    """Extrait les valeurs d'un objet SQLAlchemy"""
    if not obj:
        return None
    values = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        if value is not None and not isinstance(value, (bytes, memoryview)):
            values[column.name] = str(value) if not isinstance(value, (int, float, bool)) else value
    return values

def get_model_by_table_name(table_name: str):
    """Retourne le modèle SQLAlchemy correspondant au nom de table"""
    from ..models import (
        Bien, Vehicule, Machine, Ordinateur, 
        Utilisateur, Panne, Maintenance, Composant
    )
    
    mapping = {
        'biens': Bien,
        'vehicules': Vehicule,
        'machines': Machine,
        'ordinateurs': Ordinateur,
        'utilisateurs': Utilisateur,
        'pannes': Panne,
        'maintenances': Maintenance,
        'composants': Composant,
    }
    return mapping.get(table_name)