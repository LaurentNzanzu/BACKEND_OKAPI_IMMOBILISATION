"""add enum values phase1

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-13 10:01:00.000000

Ajoute :
- EN_TEST dans etatbien (biens.etat)
- ATTENTE_STOCK dans statutbesoin (besoins.statut)
- EN_TEST dans statutpanne (pannes.statut)
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _recreate_enum(
    table: str,
    column: str,
    old_type: str,
    new_type: str,
    new_values: list[str],
) -> None:
    values_sql = ", ".join(f"'{v}'" for v in new_values)
    op.execute(f"CREATE TYPE {new_type} AS ENUM ({values_sql})")
    op.execute(
        f"ALTER TABLE {table} "
        f"ALTER COLUMN {column} TYPE {new_type} "
        f"USING {column}::text::{new_type}"
    )
    op.execute(f"DROP TYPE {old_type}")
    op.execute(f"ALTER TYPE {new_type} RENAME TO {old_type}")


def upgrade() -> None:
    _recreate_enum(
        table="biens",
        column="etat",
        old_type="etatbien",
        new_type="etatbien_new",
        new_values=[
            "NEUF",
            "BON",
            "USAGE",
            "PANNE",
            "REFORME",
            "MAINTENANCE",
            "EN_TEST",
        ],
    )

    _recreate_enum(
        table="besoins",
        column="statut",
        old_type="statutbesoin",
        new_type="statutbesoin_new",
        new_values=[
            "BROUILLON",
            "EN_VALIDATION",
            "DG_VALIDE",
            "COMPTABLE_VALIDE",
            "CAISSE_VALIDE",
            "REJETE",
            "APPROUVEE",
            "ATTENTE_STOCK",
        ],
    )

    _recreate_enum(
        table="pannes",
        column="statut",
        old_type="statutpanne",
        new_type="statutpanne_new",
        new_values=[
            "DECLAREE",
            "DIAGNOSTIQUEE",
            "EN_ATTENTE_PIECES",
            "EN_VALIDATION",
            "EN_COURS",
            "EN_TEST",
            "TERMINEE",
            "ANNULEE",
        ],
    )


def downgrade() -> None:
    _recreate_enum(
        table="pannes",
        column="statut",
        old_type="statutpanne",
        new_type="statutpanne_old",
        new_values=[
            "DECLAREE",
            "DIAGNOSTIQUEE",
            "EN_ATTENTE_PIECES",
            "EN_VALIDATION",
            "EN_COURS",
            "TERMINEE",
            "ANNULEE",
        ],
    )

    _recreate_enum(
        table="besoins",
        column="statut",
        old_type="statutbesoin",
        new_type="statutbesoin_old",
        new_values=[
            "BROUILLON",
            "EN_VALIDATION",
            "DG_VALIDE",
            "COMPTABLE_VALIDE",
            "CAISSE_VALIDE",
            "REJETE",
            "APPROUVEE",
        ],
    )

    _recreate_enum(
        table="biens",
        column="etat",
        old_type="etatbien",
        new_type="etatbien_old",
        new_values=[
            "NEUF",
            "BON",
            "USAGE",
            "PANNE",
            "REFORME",
            "MAINTENANCE",
        ],
    )
