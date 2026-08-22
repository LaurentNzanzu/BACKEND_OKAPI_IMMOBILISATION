import logging
import json
from datetime import datetime
from typing import Any, Dict
import sys

# Configuration de base du logging
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': lambda: logging.Formatter(
                '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
            )
        },
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        },
        'security': {
            'format': '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'standard',
            'stream': 'ext://sys.stdout'
        },
        'security': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/security.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'level': 'WARNING',
            'formatter': 'security'
        }
    },
    'loggers': {
        'security': {
            'handlers': ['security', 'console'],
            'level': 'WARNING',
            'propagate': False
        },
        'app.middleware': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console']
    }
}


class SecurityLogger:
    """
    Logger spécialisé pour les événements de sécurité.
    """
    @staticmethod
    def log_event(event_type: str, user_id: int, details: Dict[str, Any]):
        """
        Log un événement de sécurité avec structure JSON.
        """
        log_entry = {
            "event_type": event_type,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details
        }
        
        logger = logging.getLogger("security")
        logger.warning(json.dumps(log_entry))
    
    @staticmethod
    def log_compromise(user_id: int, session_uuid: str, fingerprint_sent: str, fingerprint_stored: str, ip: str, user_agent: str):
        """
        Log spécifique pour une détection de compromission.
        """
        log_entry = {
            "event_type": "SECURITY_COMPROMISE",
            "user_id": user_id,
            "session_uuid": session_uuid,
            "fingerprint_sent": fingerprint_sent,
            "fingerprint_stored": fingerprint_stored,
            "ip_address": ip,
            "user_agent": user_agent,
            "timestamp": datetime.utcnow().isoformat(),
            "action": "all_sessions_revoked"
        }
        
        logger = logging.getLogger("security")
        logger.critical(json.dumps(log_entry))


# Exemple d'utilisation
# SecurityLogger.log_event("session_created", user_id, {"session_uuid": session_uuid, "ip": ip_address})
# SecurityLogger.log_compromise(user_id, session_uuid, fingerprint_sent, fingerprint_stored, ip, user_agent)