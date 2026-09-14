# alembic/versions/xxxx_sprint0_multi_tenant_projets.py
"""Sprint 0 — Multi-tenant + Projets + Permissions flotte

Revision ID: sprint0_fondations
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # 1. Créer tables organisations, abonnements_facturation, projets, workflow_etapes
    # (via op.create_table ou autogenerate)

    # 2. Ajouter organisation_id en nullable + index
    for table in [
        "utilisateurs", "biens", "mouvements_bien", "maintenances", "pannes",
        "amortissements", "ecritures_comptables", "budgets", "caisses",
        "notifications", "journal_evenements_immobilisation", "validations",
    ]:
        op.add_column(table, sa.Column("organisation_id", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_organisation_id", table, ["organisation_id"])
        op.create_foreign_key(
            f"fk_{table}_organisation_id",
            table, "organisations",
            ["organisation_id"], ["id"],
            ondelete="SET NULL",
        )

    # 3. Ajouter id_projet
    for table in ["budgets", "besoins", "mouvements_bien"]:
        op.add_column(table, sa.Column("id_projet", sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_id_projet", table, ["id_projet"])
        op.create_foreign_key(
            f"fk_{table}_id_projet",
            table, "projets",
            ["id_projet"], ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    # Opérations inverses
    ...