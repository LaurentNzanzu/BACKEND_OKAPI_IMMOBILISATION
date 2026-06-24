"""corrections comptables OHADA + statut comptable bien

Revision ID: f5b6c7d8e9f0
Revises: f4d5e6f7a8b9
Create Date: 2026-06-13 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "f4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Comptes dépréciation OHADA
    op.execute(
        """
        UPDATE regles_amortissement
        SET compte_depreciation = '2944'
        WHERE compte_depreciation = '29' OR compte_depreciation IS NULL
        """
    )

    # Colonnes statut comptable sur biens
    op.add_column("biens", sa.Column("statut_comptable", sa.String(30), server_default="ACTIF"))
    op.add_column("biens", sa.Column("cumul_amortissement", sa.Numeric(15, 2), server_default="0"))
    op.add_column("biens", sa.Column("cumul_depreciation", sa.Numeric(15, 2), server_default="0"))

    op.create_check_constraint(
        "check_statut_comptable",
        "biens",
        "statut_comptable IN ('ACTIF', 'EN_AMORTISSEMENT', 'EN_DEPRECIATION', 'CEDE', 'MIS_AU_REBUT')",
    )

    # Nouveaux types d'opération comptable
    op.execute("ALTER TYPE typeoperationenum ADD VALUE IF NOT EXISTS 'ACQUISITION'")
    op.execute("ALTER TYPE typeoperationenum ADD VALUE IF NOT EXISTS 'REPRISE_DEPRECIATION'")


def downgrade() -> None:
    op.drop_constraint("check_statut_comptable", "biens", type_="check")
    op.drop_column("biens", "cumul_depreciation")
    op.drop_column("biens", "cumul_amortissement")
    op.drop_column("biens", "statut_comptable")
