"""add id_panne to maintenances

Revision ID: f1a2b3c4d5e6
Revises: 9c70cd17da4b
Create Date: 2026-06-13 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "9c70cd17da4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "maintenances",
        sa.Column("id_panne", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_maintenances_id_panne_pannes",
        "maintenances",
        "pannes",
        ["id_panne"],
        ["id_panne"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_maintenance_panne",
        "maintenances",
        ["id_panne"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_maintenance_panne", table_name="maintenances")
    op.drop_constraint(
        "fk_maintenances_id_panne_pannes",
        "maintenances",
        type_="foreignkey",
    )
    op.drop_column("maintenances", "id_panne")
