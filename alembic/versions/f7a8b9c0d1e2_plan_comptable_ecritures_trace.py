"""plan comptable + colonnes traçabilité écritures

Revision ID: f7a8b9c0d1e2
Revises: f6c7d8e9f0a1
Create Date: 2026-06-13 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "f6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMPTES_SYSCOHADA = [
    ("244", "Immobilisations corporelles", "2", "actif"),
    ("481", "Fournisseurs d'immobilisations", "4", "passif"),
    ("512", "Banques", "5", "actif"),
    ("681", "Dotations aux amortissements", "6", "charge"),
    ("6914", "Dotations aux dépréciations", "6", "charge"),
    ("2944", "Dépréciations des immobilisations corporelles", "2", "actif"),
    ("7914", "Reprises de dépréciations", "7", "produit"),
    ("81", "Valeurs comptables des cessions d'éléments d'actif (HAO)", "8", "charge"),
    ("82", "Produits des cessions d'éléments d'actif (HAO)", "8", "produit"),
    ("654", "Valeurs comptables des cessions courantes", "6", "charge"),
    ("754", "Produits des cessions courantes", "7", "produit"),
]


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    tables = set(insp.get_table_names())

    if "plan_comptable" not in tables:
        op.create_table(
            "plan_comptable",
            sa.Column("numero", sa.String(10), primary_key=True),
            sa.Column("libelle", sa.String(255), nullable=False),
            sa.Column("classe", sa.String(1), nullable=False),
            sa.Column("type", sa.String(20)),
        )
        op.create_index("ix_plan_comptable_numero", "plan_comptable", ["numero"])

        plan_table = sa.table(
            "plan_comptable",
            sa.column("numero", sa.String),
            sa.column("libelle", sa.String),
            sa.column("classe", sa.String),
            sa.column("type", sa.String),
        )
        op.bulk_insert(
            plan_table,
            [
                {"numero": n, "libelle": l, "classe": c, "type": t}
                for n, l, c, t in COMPTES_SYSCOHADA
            ],
        )

    existing_cols = {c["name"] for c in insp.get_columns("ecritures_comptables")}
    with op.batch_alter_table("ecritures_comptables", schema=None) as batch_op:
        if "journal" not in existing_cols:
            batch_op.add_column(sa.Column("journal", sa.String(20), nullable=True))
        if "periode_comptable" not in existing_cols:
            batch_op.add_column(sa.Column("periode_comptable", sa.String(7), nullable=True))
        if "reference_id" not in existing_cols:
            batch_op.add_column(sa.Column("reference_id", sa.Integer(), nullable=True))
        if "cree_par" not in existing_cols:
            batch_op.add_column(
                sa.Column("cree_par", sa.Integer(), sa.ForeignKey("utilisateurs.id"), nullable=True)
            )
        if "date_creation" not in existing_cols:
            batch_op.add_column(sa.Column("date_creation", sa.DateTime(), nullable=True))
        if "valide_par" not in existing_cols:
            batch_op.add_column(
                sa.Column("valide_par", sa.Integer(), sa.ForeignKey("utilisateurs.id"), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("ecritures_comptables", schema=None) as batch_op:
        batch_op.drop_column("valide_par")
        batch_op.drop_column("date_creation")
        batch_op.drop_column("cree_par")
        batch_op.drop_column("reference_id")
        batch_op.drop_column("periode_comptable")
        batch_op.drop_column("journal")

    op.drop_index("ix_plan_comptable_numero", table_name="plan_comptable")
    op.drop_table("plan_comptable")
