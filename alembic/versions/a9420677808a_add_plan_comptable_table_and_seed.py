# backend/alembic/versions/a9420677808a_add_plan_comptable_table_and_seed.py
"""add_plan_comptable_table_and_seed

Revision ID: a9420677808a
Revises: 6b933e1ac0e6
Create Date: 2026-06-20 16:33:05.432149

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "a9420677808a"
down_revision: Union[str, Sequence[str], None] = "6b933e1ac0e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name, column_name):
    """Vérifie si une colonne existe dans une table"""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema - Ajout des colonnes manquantes à plan_comptable"""
    
    # Vérifier si la table existe
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'plan_comptable' not in inspector.get_table_names():
        # Si la table n'existe pas, la créer
        op.create_table(
            'plan_comptable',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('numero', sa.String(length=10), nullable=False),
            sa.Column('libelle', sa.String(length=255), nullable=False),
            sa.Column('classe', sa.String(length=1), nullable=False),
            sa.Column('type', sa.String(length=20), nullable=False),
            sa.Column('est_actif', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('numero', name='uq_plan_comptable_numero')
        )
        # Créer les index
        op.create_index(op.f('ix_plan_comptable_numero'), 'plan_comptable', ['numero'], unique=True)
        op.create_index(op.f('ix_plan_comptable_id'), 'plan_comptable', ['id'], unique=False)
        op.create_index('ix_plan_comptable_classe', 'plan_comptable', ['classe'], unique=False)
        op.create_index('ix_plan_comptable_type', 'plan_comptable', ['type'], unique=False)
    else:
        # La table existe, ajouter les colonnes manquantes
        if not column_exists('plan_comptable', 'id'):
            op.add_column('plan_comptable', sa.Column('id', sa.Integer(), nullable=True))
        
        if not column_exists('plan_comptable', 'est_actif'):
            op.add_column('plan_comptable', sa.Column('est_actif', sa.Boolean(), server_default='true', nullable=False))
        
        if not column_exists('plan_comptable', 'created_at'):
            op.add_column('plan_comptable', sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False))
        
        if not column_exists('plan_comptable', 'updated_at'):
            op.add_column('plan_comptable', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False))
        
        # Mettre à jour les valeurs existantes
        op.execute("UPDATE plan_comptable SET est_actif = true WHERE est_actif IS NULL")
        op.execute("UPDATE plan_comptable SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
        op.execute("UPDATE plan_comptable SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
        
        # Créer les index si non existants
        # Note: Les index sont créés automatiquement si la table existe déjà
        # Mais on peut les recréer si nécessaire


def downgrade() -> None:
    """Downgrade schema - Suppression des colonnes ajoutées"""
    
    # Supprimer les index
    op.drop_index('ix_plan_comptable_type', table_name='plan_comptable', if_exists=True)
    op.drop_index('ix_plan_comptable_classe', table_name='plan_comptable', if_exists=True)
    op.drop_index(op.f('ix_plan_comptable_id'), table_name='plan_comptable', if_exists=True)
    op.drop_index(op.f('ix_plan_comptable_numero'), table_name='plan_comptable', if_exists=True)
    
    # Supprimer les colonnes
    op.drop_column('plan_comptable', 'updated_at', if_exists=True)
    op.drop_column('plan_comptable', 'created_at', if_exists=True)
    op.drop_column('plan_comptable', 'est_actif', if_exists=True)
    op.drop_column('plan_comptable', 'id', if_exists=True)