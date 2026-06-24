# backend/alembic/versions/6b933e1ac0e6_ajout_des_champs_mode_paiement_.py
"""Ajout des champs mode_paiement, fournisseur_id et table fournisseurs

Revision ID: 6b933e1ac0e6
Revises: f9b0c1d2e3f4
Create Date: 2026-06-18 16:52:37.338264

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6b933e1ac0e6"
down_revision: Union[str, Sequence[str], None] = "f9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ============================================================
    # 1. CRÉATION DE LA TABLE FOURNISSEURS
    # ============================================================
    op.create_table(
        "fournisseurs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nom", sa.String(length=200), nullable=False),
        sa.Column("adresse", sa.String(length=500), nullable=True),
        sa.Column("telephone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=100), nullable=True),
        sa.Column("numero_contribuable", sa.String(length=50), nullable=True),
        sa.Column(
            "date_creation", 
            sa.DateTime(), 
            server_default=sa.text("CURRENT_TIMESTAMP"), 
            nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fournisseurs_id"), "fournisseurs", ["id"], unique=False)
    op.create_index(op.f("ix_fournisseurs_nom"), "fournisseurs", ["nom"], unique=False)

    # ============================================================
    # 2. AJOUT DES COLONNES À LA TABLE BIENS
    # ============================================================
    op.add_column(
        "biens", 
        sa.Column("mode_paiement", sa.String(length=20), server_default="credit", nullable=False)
    )
    op.add_column(
        "biens", 
        sa.Column("fournisseur_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "biens", 
        sa.Column("devise", sa.String(length=10), server_default="FCFA", nullable=False)
    )

    # ============================================================
    # 3. AJOUT DE LA CLÉ ÉTRANGÈRE
    # ============================================================
    op.create_foreign_key(
        "fk_biens_fournisseur_id",
        "biens",
        "fournisseurs",
        ["fournisseur_id"],
        ["id"],
        ondelete="SET NULL"
    )

    # ============================================================
    # 4. MISE À JOUR DES INDEX EXISTANTS (optionnel)
    # ============================================================
    # Recréer les index qui pourraient avoir été supprimés
    op.create_index(
        op.f("ix_fournitures_pieces_id_fourniture"),
        "fournitures_pieces",
        ["id_fourniture"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fournitures_pieces_id_besoin"),
        "fournitures_pieces",
        ["id_besoin"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fournitures_pieces_id_magasinier"),
        "fournitures_pieces",
        ["id_magasinier"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fournitures_pieces_id_piece"),
        "fournitures_pieces",
        ["id_piece"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fournitures_pieces_date_fourniture"),
        "fournitures_pieces",
        ["date_fourniture"],
        unique=False,
    )
    op.create_index(
        op.f("ix_maintenances_id_panne"),
        "maintenances",
        ["id_panne"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # ============================================================
    # 1. SUPPRESSION DE LA CLÉ ÉTRANGÈRE
    # ============================================================
    op.drop_constraint("fk_biens_fournisseur_id", "biens", type_="foreignkey")

    # ============================================================
    # 2. SUPPRESSION DES COLONNES
    # ============================================================
    op.drop_column("biens", "devise")
    op.drop_column("biens", "fournisseur_id")
    op.drop_column("biens", "mode_paiement")

    # ============================================================
    # 3. SUPPRESSION DE LA TABLE FOURNISSEURS
    # ============================================================
    op.drop_index(op.f("ix_fournisseurs_nom"), table_name="fournisseurs")
    op.drop_index(op.f("ix_fournisseurs_id"), table_name="fournisseurs")
    op.drop_table("fournisseurs")

    # ============================================================
    # 4. RESTAURATION DES INDEX (si nécessaire)
    # ============================================================
    op.drop_index(op.f("ix_maintenances_id_panne"), table_name="maintenances")
    op.drop_index(op.f("ix_fournitures_pieces_date_fourniture"), table_name="fournitures_pieces")
    op.drop_index(op.f("ix_fournitures_pieces_id_piece"), table_name="fournitures_pieces")
    op.drop_index(op.f("ix_fournitures_pieces_id_magasinier"), table_name="fournitures_pieces")
    op.drop_index(op.f("ix_fournitures_pieces_id_besoin"), table_name="fournitures_pieces")
    op.drop_index(op.f("ix_fournitures_pieces_id_fourniture"), table_name="fournitures_pieces")