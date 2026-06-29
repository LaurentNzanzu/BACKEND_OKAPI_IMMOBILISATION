# backend/app/models/cession.py
from sqlalchemy import Column, Integer, ForeignKey, Date, String, Numeric, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from ..core.database import Base

class TypeCession(enum.Enum):
    """Type de cession"""
    COURANTE = "courante"
    NON_COURANTE = "non_courante"
    MISE_AU_REBUT = "mise_au_rebut"

class StatutCession(enum.Enum):
    """Statut d'une cession"""
    ELIGIBLE = "ELIGIBLE"
    EN_ATTENTE_VALIDATION = "EN_ATTENTE_VALIDATION"
    EN_COURS = "EN_COURS"
    VALIDEE = "VALIDEE"          # NOUVEAU : Après validation comptable/caissier
    ACCORDEE = "ACCORDEE"        # Après validation DG
    REJETEE = "REJETEE"
    TERMINEE = "TERMINEE"

class ModeReglement(enum.Enum):
    """Mode de règlement"""
    COMPTANT = "comptant"
    CREDIT = "credit"
    VIREMENT = "virement"
    CHEQUE = "cheque"
    ESPECE = "espece"

class Cession(Base):
    __tablename__ = "cessions"
    
    id_cession = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    date_cession = Column(Date, nullable=False)
    prix_vente = Column(Numeric(15, 2), nullable=False)
    valeur_nette_comptable = Column(Numeric(15, 2), nullable=True)
    resultat = Column(Numeric(15, 2), nullable=True)
    acheteur = Column(String(255), nullable=True)
    mode_reglement = Column(SQLEnum(ModeReglement), nullable=True)
    type_cession = Column(SQLEnum(TypeCession), nullable=False, default=TypeCession.COURANTE)
    motif = Column(Text, nullable=True)

    # === CHAMPS WORKFLOW & TÂCHES ===
    statut = Column(SQLEnum(StatutCession), default=StatutCession.EN_ATTENTE_VALIDATION, nullable=False)
    actif_remplacement_id = Column(Integer, ForeignKey("biens.id_bien", ondelete="SET NULL"), nullable=True, index=True)
    piece_justificative_url = Column(String(500), nullable=True)
    commentaire = Column(Text, nullable=True)

    # NOUVEAU CHAMP PHASE 1.4
    date_paiement = Column(DateTime, nullable=True, comment="Date effective de l'encaissement")

    # Dates de validation par rôle
    date_validation_comptable = Column(DateTime, nullable=True)
    date_validation_caissier = Column(DateTime, nullable=True)
    date_validation_dg = Column(DateTime, nullable=True)
    date_validation_finale = Column(DateTime, nullable=True)

    # IDs des validateurs
    id_validateur_comptable = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    id_validateur_caissier = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    id_validateur_dg = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)

    # Audit
    cree_par = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relations
    bien = relationship("Bien", foreign_keys=[id_bien], back_populates="cessions")
    actif_remplacement = relationship("Bien", foreign_keys=[actif_remplacement_id])
    validateur_comptable = relationship("Utilisateur", foreign_keys=[id_validateur_comptable])
    validateur_caissier = relationship("Utilisateur", foreign_keys=[id_validateur_caissier])
    validateur_dg = relationship("Utilisateur", foreign_keys=[id_validateur_dg])
    createur = relationship("Utilisateur", foreign_keys=[cree_par])

    # Relation avec les validations (workflow)
    validations = relationship(
        "Validation",
        foreign_keys="Validation.id_bien",
        primaryjoin="and_(Validation.id_bien == Cession.id_bien, Validation.type_validation == 'CESSION')",
        viewonly=True,
        lazy="select"
    )

    # =========================================================================
    # PROPRIÉTÉS & MÉTHODES MÉTIER
    # =========================================================================

    @property
    def est_complete(self) -> bool:
        """Vérifie si toutes les validations sont effectuées."""
        return self.statut in [StatutCession.ACCORDEE, StatutCession.REJETEE, StatutCession.TERMINEE]

    @property
    def est_approuvee(self) -> bool:
        """Vérifie si la cession est approuvée."""
        return self.statut == StatutCession.ACCORDEE

    def approuver(self, validateur_id: int, role: str):
        """Approuve la cession par un validateur."""
        if role == "COMPTABLE":
            self.id_validateur_comptable = validateur_id
            self.date_validation_comptable = datetime.utcnow()
        elif role == "CAISSIER":
            self.id_validateur_caissier = validateur_id
            self.date_validation_caissier = datetime.utcnow()
            # Le caissier confirme l'encaissement
            self.date_paiement = datetime.utcnow() 
            self.statut = StatutCession.VALIDEE
        elif role == "DG":
            self.id_validateur_dg = validateur_id
            self.date_validation_dg = datetime.utcnow()
            self.date_validation_finale = datetime.utcnow()
            self.statut = StatutCession.ACCORDEE
        
        self.updated_at = datetime.utcnow()

    def rejeter(self, validateur_id: int, role: str, motif: str):
        """Rejette la cession par un validateur."""
        if role == "COMPTABLE":
            self.id_validateur_comptable = validateur_id
            self.date_validation_comptable = datetime.utcnow()
        elif role == "CAISSIER":
            self.id_validateur_caissier = validateur_id
            self.date_validation_caissier = datetime.utcnow()
        elif role == "DG":
            self.id_validateur_dg = validateur_id
            self.date_validation_dg = datetime.utcnow()
            self.date_validation_finale = datetime.utcnow()
        
        self.statut = StatutCession.REJETEE
        self.motif = motif
        self.updated_at = datetime.utcnow()

    def marquer_terminee(self):
        """Marque la cession comme terminée (après sortie effective du bien)."""
        self.statut = StatutCession.TERMINEE
        self.updated_at = datetime.utcnow()

    def calculer_resultat(self):
        """Calcule le résultat de la cession (PV - VNC)."""
        if self.prix_vente is not None and self.valeur_nette_comptable is not None:
            self.resultat = self.prix_vente - self.valeur_nette_comptable
        return self.resultat