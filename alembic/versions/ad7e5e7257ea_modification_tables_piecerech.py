"""modification_tables_pieceRech

Revision ID: ad7e5e7257ea
Revises:
Create Date: 2026-06-06 14:30:01.489761

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

typecompatible_enum = ENUM('vehicule', 'ordinateur', 'machine_production', name='typecompatible')

revision: str = "ad7e5e7257ea"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # 1. D'abord, nettoyer les données existantes
    # Corriger 'vehi' en 'vehicule'
    conn.execute(
        sa.text("UPDATE pieces_rechange SET compatible_avec = 'vehicule' WHERE compatible_avec = 'vehi'")
    )
    
    # Pour toute autre valeur non conforme, mettre 'vehicule' par défaut
    conn.execute(
        sa.text("UPDATE pieces_rechange SET compatible_avec = 'vehicule' WHERE compatible_avec IS NULL OR compatible_avec = ''")
    )
    
    # 2. Ajouter les nouvelles colonnes
    op.add_column("pieces_rechange", sa.Column("numero_serie", sa.String(length=50), nullable=True))
    op.add_column("pieces_rechange", sa.Column("fournisseur", sa.String(length=200), nullable=True))
    
    # 3. Générer des numéros de série pour les lignes existantes
    result = conn.execute(sa.text("SELECT id_piece FROM pieces_rechange"))
    rows = result.fetchall()
    for row in rows:
        # row est un tuple, on accède par index
        piece_id = row[0]
        new_serie = f"SERIE{str(piece_id).zfill(8)}"
        conn.execute(
            sa.text("UPDATE pieces_rechange SET numero_serie = :serie WHERE id_piece = :id"),
            {"serie": new_serie, "id": piece_id}
        )
    
    # 4. Rendre numero_serie NOT NULL avec contrainte unique
    op.alter_column("pieces_rechange", "numero_serie", nullable=False)
    op.create_index(op.f("ix_pieces_rechange_numero_serie"), "pieces_rechange", ["numero_serie"], unique=True)
    
    # 5. Créer l'ENUM
    typecompatible_enum.create(op.get_bind(), checkfirst=True)
    
    # 6. Convertir la colonne compatible_avec en ENUM
    op.execute(sa.text("""
        ALTER TABLE pieces_rechange 
        ALTER COLUMN compatible_avec TYPE typecompatible 
        USING compatible_avec::typecompatible
    """))
    
    # 7. Migrer les données de fournisseur_principal
    # Vérifier si la colonne fournisseur_principal existe
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'pieces_rechange' AND column_name = 'fournisseur_principal'
    """))
    fournisseur_exists = result.fetchone() is not None
    
    if fournisseur_exists:
        conn.execute(sa.text("""
            UPDATE pieces_rechange SET fournisseur = fournisseur_principal 
            WHERE fournisseur_principal IS NOT NULL
        """))
    
    # 8. Supprimer les anciennes colonnes
    op.drop_column("pieces_rechange", "reference")
    op.drop_column("pieces_rechange", "description")
    op.drop_column("pieces_rechange", "delai_livraison_jours")
    
    if fournisseur_exists:
        op.drop_column("pieces_rechange", "fournisseur_principal")


def downgrade() -> None:
    conn = op.get_bind()
    
    # 1. Ajouter l'ancienne colonne compatible_avec comme VARCHAR
    op.add_column("pieces_rechange", sa.Column("compatible_avec_old", sa.VARCHAR(length=200), nullable=True))
    
    # 2. Convertir les données de l'ENUM vers VARCHAR
    conn.execute(sa.text("""
        UPDATE pieces_rechange SET compatible_avec_old = 'VEHICULE'
        WHERE compatible_avec = 'vehicule'
    """))
    conn.execute(sa.text("""
        UPDATE pieces_rechange SET compatible_avec_old = 'ORDINATEUR'
        WHERE compatible_avec = 'ordinateur'
    """))
    conn.execute(sa.text("""
        UPDATE pieces_rechange SET compatible_avec_old = 'MACHINE_PRODUCTION'
        WHERE compatible_avec = 'machine_production'
    """))
    
    # 3. Supprimer l'ancienne colonne compatible_avec
    op.drop_column("pieces_rechange", "compatible_avec")
    op.alter_column("pieces_rechange", "compatible_avec_old", new_column_name="compatible_avec")
    
    # 4. Recréer les anciennes colonnes
    op.add_column("pieces_rechange", sa.Column("reference", sa.VARCHAR(length=100), nullable=True))
    op.add_column("pieces_rechange", sa.Column("description", sa.TEXT(), nullable=True))
    op.add_column("pieces_rechange", sa.Column("delai_livraison_jours", sa.INTEGER(), nullable=True))
    op.add_column("pieces_rechange", sa.Column("fournisseur_principal", sa.VARCHAR(length=200), nullable=True))
    
    # 5. Restaurer les données
    result = conn.execute(sa.text("SELECT id_piece, numero_serie FROM pieces_rechange WHERE numero_serie IS NOT NULL"))
    rows = result.fetchall()
    for row in rows:
        piece_id = row[0]
        numero_serie = row[1]
        conn.execute(
            sa.text("UPDATE pieces_rechange SET reference = :ref WHERE id_piece = :id"),
            {"ref": numero_serie, "id": piece_id}
        )
    
    conn.execute(sa.text("UPDATE pieces_rechange SET fournisseur_principal = fournisseur WHERE fournisseur IS NOT NULL"))
    conn.execute(sa.text("UPDATE pieces_rechange SET delai_livraison_jours = 7 WHERE delai_livraison_jours IS NULL"))
    
    # 6. Rendre reference NOT NULL
    op.alter_column("pieces_rechange", "reference", nullable=False)
    op.create_index(op.f("ix_pieces_rechange_reference"), "pieces_rechange", ["reference"], unique=True)
    
    # 7. Supprimer les nouvelles colonnes
    op.drop_index(op.f("ix_pieces_rechange_numero_serie"), table_name="pieces_rechange")
    op.drop_column("pieces_rechange", "numero_serie")
    op.drop_column("pieces_rechange", "fournisseur")
    
    # 8. Supprimer l'ENUM
    try:
        typecompatible_enum.drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass