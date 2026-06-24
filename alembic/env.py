# backend/alembic/env.py
# -*- coding: utf-8 -*-
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import sys
import os

# Ajouter le chemin du projet
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Importer vos modèles
from app.core.database import Base
from app.models.bien import Bien
from app.models.panne import Panne
from app.models.maintenance import Maintenance
from app.models.amortissement import Amortissement
from app.models.piece_rechange import PieceRechange
from app.models.mouvement_bien import MouvementBien
from app.models.besoin import Besoin
from app.models.ligne_besoin import LigneBesoin
from app.models.validation import Validation
from app.models.utilisateur import Utilisateur
from app.models.role import Role
from app.models.notification import Notification
from app.models.decision_ia import DecisionIA
from app.models.fourniture_piece import FourniturePiece

# Configuration Alembic
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()