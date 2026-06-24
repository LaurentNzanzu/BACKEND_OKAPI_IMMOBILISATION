"""add notification enum values phase2

Revision ID: f4d5e6f7a8b9
Revises: f3c4d5e6f7a8
Create Date: 2026-06-13 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "f4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "f3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_VALUES = [
    "FOURNITURE_EN_ATTENTE",
    "FOURNITURE_VALIDEE",
    "STOCK_INSUFFISANT",
    "BIEN_EN_TEST",
    "PANNE_RESOLUE",
]


def upgrade() -> None:
    op.execute("ALTER TYPE typenotificationenum ADD VALUE IF NOT EXISTS 'FOURNITURE_EN_ATTENTE'")
    op.execute("ALTER TYPE typenotificationenum ADD VALUE IF NOT EXISTS 'FOURNITURE_VALIDEE'")
    op.execute("ALTER TYPE typenotificationenum ADD VALUE IF NOT EXISTS 'STOCK_INSUFFISANT'")
    op.execute("ALTER TYPE typenotificationenum ADD VALUE IF NOT EXISTS 'BIEN_EN_TEST'")
    op.execute("ALTER TYPE typenotificationenum ADD VALUE IF NOT EXISTS 'PANNE_RESOLUE'")


def downgrade() -> None:
    pass
