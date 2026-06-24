"""compatible

Revision ID: 9c70cd17da4b
Revises: ad7e5e7257ea
Create Date: 2026-06-06 16:44:42.342211

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9c70cd17da4b"
down_revision: Union[str, Sequence[str], None] = "ad7e5e7257ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE typedecisionenum AS ENUM (
                'HEALTH_SCORE', 'PREDICTION_PANNE', 'ACHAT_RECOMMENDE',
                'DECISION_STRATEGIQUE', 'SCAN_PIECE'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        UPDATE decisions_ia
        SET type_decision = 'ACHAT_RECOMMENDE'
        WHERE type_decision = 'ACHAT_RECOMMANDE'
        """
    )
    op.execute(
        """
        ALTER TABLE decisions_ia
        ALTER COLUMN type_decision TYPE typedecisionenum
        USING type_decision::typedecisionenum
        """
    )

    op.create_index(
        op.f("ix_decisions_ia_id_decision"),
        "decisions_ia",
        ["id_decision"],
        unique=False,
    )

    op.execute(
        """
        ALTER TABLE pieces_rechange
        ALTER COLUMN compatible_avec TYPE typecompatible
        USING compatible_avec::typecompatible
        """
    )
    op.alter_column("pieces_rechange", "compatible_avec", nullable=False)
    op.drop_column("pieces_rechange", "compatible_temp")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "pieces_rechange",
        sa.Column(
            "compatible_temp", sa.VARCHAR(length=50), autoincrement=False, nullable=True
        ),
    )
    op.execute(
        """
        ALTER TABLE pieces_rechange
        ALTER COLUMN compatible_avec TYPE VARCHAR(50)
        USING compatible_avec::text
        """
    )
    op.alter_column("pieces_rechange", "compatible_avec", nullable=True)
    op.drop_index(op.f("ix_decisions_ia_id_decision"), table_name="decisions_ia")
    op.execute(
        """
        ALTER TABLE decisions_ia
        ALTER COLUMN type_decision TYPE VARCHAR(50)
        USING type_decision::text
        """
    )
