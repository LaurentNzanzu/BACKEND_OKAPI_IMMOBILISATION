# backend/app/models/mouvement_caisse.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class MouvementCaisse(Base):
    __tablename__ = "mouvements_caisse"

    id_mouvement = Column(Integer, primary_key=True, index=True)
    id_caisse = Column(Integer, ForeignKey("caisses.id_caisse", ondelete="CASCADE"), nullable=False)
    numero_piece = Column(String(50), unique=True, nullable=False)
    date_mouvement = Column(DateTime, default=datetime.utcnow, nullable=False)
    type_mouvement = Column(String(10), nullable=False)  # 'ENTREE' ou 'SORTIE'
    montant = Column(Float, nullable=False)
    solde_avant = Column(Float, nullable=False)
    solde_apres = Column(Float, nullable=False)
    motif = Column(Text, nullable=False)
    origine_type = Column(String(30), nullable=False)  # 'BESOIN', 'MAINTENANCE', 'STOCK', 'ACQUISITION', 'CESSION', 'AMORTISSEMENT'
    origine_id = Column(Integer, nullable=False)
    mode_reglement = Column(String(20), default="ESPECES", nullable=False)
    beneficiaire = Column(String(100), nullable=True)
    piece_jointe_url = Column(String(255), nullable=True)
    statut = Column(String(20), default="BROUILLON", nullable=False)
    valide_par = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    date_validation = Column(DateTime, nullable=True)

    caisse = relationship("Caisse")
    validateur = relationship("Utilisateur", foreign_keys=[valide_par])
    piece_justificative = relationship("PieceJustificative", back_populates="mouvement", uselist=False, cascade="all, delete-orphan")
