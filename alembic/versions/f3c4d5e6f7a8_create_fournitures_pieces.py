"""create fournitures_pieces table

Revision ID: f3c4d5e6f7a8
Revises: f2b3c4d5e6f7
Create Date: 2026-06-13 10:02:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "f2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUT_FOURNITURE_VALUES = (
    "EN_ATTENTE",
    "FOURNIE",
    "PARTIELLE",
    "REFUSEE",
    "ANNULEE",
)

statut_fourniture_enum = postgresql.ENUM(
    *STATUT_FOURNITURE_VALUES,
    name="statut_fourniture",
    create_type=False,
)


def upgrade() -> None:
    statut_fourniture_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "fournitures_pieces",
        sa.Column("id_fourniture", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_besoin", sa.Integer(), nullable=False),
        sa.Column("id_piece", sa.Integer(), nullable=False),
        sa.Column("quantite_demandee", sa.Integer(), nullable=False),
        sa.Column("quantite_fournie", sa.Integer(), nullable=True),
        sa.Column("date_fourniture", sa.DateTime(), nullable=True),
        sa.Column("id_magasinier", sa.Integer(), nullable=True),
        sa.Column(
            "statut",
            statut_fourniture_enum,
            nullable=False,
            server_default="EN_ATTENTE",
        ),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column(
            "date_creation",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column("date_modification", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "quantite_demandee > 0",
            name="ck_fourniture_quantite_demandee_positive",
        ),
        sa.ForeignKeyConstraint(
            ["id_besoin"],
            ["besoins.id_besoin"],
            name="fk_fourniture_besoin",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_piece"],
            ["pieces_rechange.id_piece"],
            name="fk_fourniture_piece",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id_magasinier"],
            ["utilisateurs.id"],
            name="fk_fourniture_magasinier",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id_fourniture"),
    )

    op.create_index(
        "idx_fourniture_besoin",
        "fournitures_pieces",
        ["id_besoin"],
        unique=False,
    )
    op.create_index(
        "idx_fourniture_statut",
        "fournitures_pieces",
        ["statut"],
        unique=False,
    )
    op.create_index(
        "idx_fourniture_piece",
        "fournitures_pieces",
        ["id_piece"],
        unique=False,
    )
    op.create_index(
        "idx_fourniture_magasinier",
        "fournitures_pieces",
        ["id_magasinier"],
        unique=False,
    )
    op.create_index(
        "idx_fourniture_date",
        "fournitures_pieces",
        ["date_fourniture"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_fourniture_date", table_name="fournitures_pieces")
    op.drop_index("idx_fourniture_magasinier", table_name="fournitures_pieces")
    op.drop_index("idx_fourniture_piece", table_name="fournitures_pieces")
    op.drop_index("idx_fourniture_statut", table_name="fournitures_pieces")
    op.drop_index("idx_fourniture_besoin", table_name="fournitures_pieces")
    op.drop_table("fournitures_pieces")
    statut_fourniture_enum.drop(op.get_bind(), checkfirst=True)
