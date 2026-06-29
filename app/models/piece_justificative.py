from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Boolean, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class TypePieceJustificative(enum.Enum):
    """Types de pièces justificatives."""
    ACQUISITION = "ACQUISITION"          # Reçu d'achat / Facture d'acquisition
    FONDS = "FONDS"                       # Justificatif d'existence des fonds
    DECAISSEMENT = "DECAISSEMENT"         # Bon de décaissement / Preuve de paiement
    AMORTISSEMENT = "AMORTISSEMENT"       # Justificatif d'amortissement
    CESSION = "CESSION"                   # Acte de cession
    MAINTENANCE = "MAINTENANCE"           # Facture de maintenance / Réparation
    STOCK = "STOCK"                       # Fiche de stock
    INVENTAIRE = "INVENTAIRE"             # Fiche d'inventaire


class StatutPieceJustificative(enum.Enum):
    """Statut d'une pièce justificative."""
    BROUILLON = "BROUILLON"               # En cours de téléchargement
    SOUMIS = "SOUMIS"                     # Soumis pour validation
    VALIDE = "VALIDE"                     # Validé (non modifiable)
    REJETE = "REJETE"                     # Rejeté
    ARCHIVE = "ARCHIVE"                   # Archivé


class PieceJustificative(Base):
    __tablename__ = "pieces_justificatives"
    
    id_piece = Column(Integer, primary_key=True, index=True)
    
    # Type et statut
    type_piece = Column(Enum(TypePieceJustificative), nullable=False)
    statut = Column(Enum(StatutPieceJustificative), default=StatutPieceJustificative.BROUILLON)
    
    # Informations du document
    titre = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    numero_reference = Column(String(100), nullable=True)  # Numéro de facture, bon, etc.
    motif_rejet = Column(Text, nullable=True)
    
    # Fichier
    fichier_nom = Column(String(255), nullable=False)
    fichier_url = Column(String(500), nullable=False)
    fichier_taille = Column(Float, nullable=True)  # Taille en Ko
    fichier_type = Column(String(100), nullable=True)  # MIME type
    
    # Dates
    date_document = Column(DateTime, nullable=True)  # Date du document original
    date_upload = Column(DateTime, default=datetime.utcnow)
    date_validation = Column(DateTime, nullable=True)
    
    # Signature électronique
    signature_electronique = Column(String(255), nullable=True)  # Hash de signature
    est_signee = Column(Boolean, default=False)
    date_signature = Column(DateTime, nullable=True)
    
    # Liens vers les transactions
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="SET NULL"), nullable=True)
    id_besoin = Column(Integer, ForeignKey("besoins.id_besoin", ondelete="SET NULL"), nullable=True)
    id_amortissement = Column(Integer, ForeignKey("amortissements.id_amortissement", ondelete="SET NULL"), nullable=True)
    id_cession = Column(Integer, ForeignKey("cessions.id_cession", ondelete="SET NULL"), nullable=True)
    id_maintenance = Column(Integer, ForeignKey("maintenances.id_maintenance", ondelete="SET NULL"), nullable=True)
    id_ecriture = Column(Integer, ForeignKey("ecritures_comptables.id_ecriture", ondelete="SET NULL"), nullable=True)
    
    # Utilisateurs
    upload_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    valide_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    signe_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    
    # Relations
    upload_par = relationship("Utilisateur", foreign_keys=[upload_par_id])
    valide_par = relationship("Utilisateur", foreign_keys=[valide_par_id])
    signe_par = relationship("Utilisateur", foreign_keys=[signe_par_id])
    bien = relationship("Bien", foreign_keys=[id_bien])
    besoin = relationship("Besoin", foreign_keys=[id_besoin])
    amortissement = relationship("Amortissement", foreign_keys=[id_amortissement])
    cession = relationship("Cession", foreign_keys=[id_cession])
    maintenance = relationship("Maintenance", foreign_keys=[id_maintenance])
    ecriture = relationship("EcritureComptable", foreign_keys=[id_ecriture])
    
    def valider(self, utilisateur_id: int):
        """Valide la pièce justificative."""
        if self.statut == StatutPieceJustificative.VALIDE:
            raise ValueError("Cette pièce est déjà validée")
        self.statut = StatutPieceJustificative.VALIDE
        self.date_validation = datetime.utcnow()
        self.valide_par_id = utilisateur_id
    
    def rejeter(self, utilisateur_id: int, motif: str):
        """Rejette la pièce justificative."""
        self.statut = StatutPieceJustificative.REJETE
        self.date_validation = datetime.utcnow()
        self.valide_par_id = utilisateur_id
        self.motif_rejet = motif
    
    def signer(self, utilisateur_id: int, signature: str):
        """Appose une signature électronique."""
        if self.statut != StatutPieceJustificative.VALIDE:
            raise ValueError("La pièce doit être validée avant signature")
        self.signature_electronique = signature
        self.est_signee = True
        self.date_signature = datetime.utcnow()
        self.signe_par_id = utilisateur_id
