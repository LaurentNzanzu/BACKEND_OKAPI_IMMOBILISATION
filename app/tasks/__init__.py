# backend/app/tasks/__init__.py
from .cron_scores import calculer_scores_fiabilite, init_scheduler as init_scores_scheduler
from .cron_alertes_vnc import verifier_alertes_vnc, init_scheduler as init_alertes_scheduler
from .cron_projections import generer_projections, init_scheduler as init_projections_scheduler

__all__ = [
    'calculer_scores_fiabilite',
    'verifier_alertes_vnc',
    'generer_projections',
    'init_scores_scheduler',
    'init_alertes_scheduler',
    'init_projections_scheduler',
]