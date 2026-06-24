"""create cessions table

Revision ID: f6c7d8e9f0a1
Revises: f5b6c7d8e9f0
Create Date: 2026-06-13 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "f5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cessions",
        sa.Column("id_cession", sa.Integer(), primary_key=True),
        sa.Column("id_bien", sa.Integer(), sa.ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False),
        sa.Column("date_cession", sa.Date(), nullable=False),
        sa.Column("prix_vente", sa.Numeric(15, 2), nullable=False),
        sa.Column("acheteur", sa.String(255)),
        sa.Column("mode_reglement", sa.String(50)),
        sa.Column("type_cession", sa.String(20), nullable=False),
        sa.Column("resultat", sa.Numeric(15, 2)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_cessions_id_cession", "cessions", ["id_cession"])


def downgrade() -> None:
    op.drop_index("ix_cessions_id_cession", table_name="cessions")
    op.drop_table("cessions")
