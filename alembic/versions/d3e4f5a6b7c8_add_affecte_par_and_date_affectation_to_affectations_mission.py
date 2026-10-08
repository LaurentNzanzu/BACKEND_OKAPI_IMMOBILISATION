"""Ajout affecte_par et date_affectation sur affectations_mission pour traçabilité

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-10-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("affectations_mission", schema=None) as batch_op:
            batch_op.add_column(sa.Column("affecte_par", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("date_affectation", sa.DateTime(), server_default=sa.func.now(), nullable=True))
            batch_op.create_index("ix_affectations_mission_affecte_par", ["affecte_par"])
            batch_op.create_foreign_key(
                "fk_affectations_mission_affecte_par",
                "utilisateurs",
                ["affecte_par"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.add_column("affectations_mission", sa.Column("affecte_par", sa.Integer(), nullable=True))
        op.add_column("affectations_mission", sa.Column("date_affectation", sa.DateTime(), server_default=sa.func.now(), nullable=True))
        op.create_index("ix_affectations_mission_affecte_par", "affectations_mission", ["affecte_par"])
        op.create_foreign_key(
            "fk_affectations_mission_affecte_par",
            "affectations_mission",
            "utilisateurs",
            ["affecte_par"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("affectations_mission", schema=None) as batch_op:
            batch_op.drop_constraint("fk_affectations_mission_affecte_par", type_="foreignkey")
            batch_op.drop_index("ix_affectations_mission_affecte_par")
            batch_op.drop_column("date_affectation")
            batch_op.drop_column("affecte_par")
    else:
        op.drop_constraint("fk_affectations_mission_affecte_par", "affectations_mission", type_="foreignkey")
        op.drop_index("ix_affectations_mission_affecte_par", table_name="affectations_mission")
        op.drop_column("affectations_mission", "date_affectation")
        op.drop_column("affectations_mission", "affecte_par")
