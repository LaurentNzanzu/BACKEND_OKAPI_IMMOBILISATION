# backend/app/models/ordre_remplacement.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class StatutOrdreRemplacement(enum.Enum):
    """Statuts possibles pour un ordre de remplacement"""
    EN_ATTENTE = "EN_ATTENTE"
    EN_COURS = "EN_COURS"
    VALIDE = "VALIDE"
    REJETE = "REJETE"
    EXECUTE = "EXECUTE"
    ANNULE = "ANNULE"


class PrioriteOrdre(enum.Enum):
    """Priorités pour un ordre de remplacement"""
    CRITIQUE = "CRITIQUE"
    URGENT = "URGENT"
    NORMALE = "NORMALE"
    BASSE = "BASSE"


class OrdreRemplacement(Base):
    __tablename__ = "ordres_remplacement"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Références
    bien_id = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False, index=True)
    alerte_vnc_id = Column(Integer, ForeignKey("alertes_vnc.id", ondelete="SET NULL"), nullable=True, index=True)
    bien_remplacement_id = Column(Integer, ForeignKey("biens.id_bien", ondelete="SET NULL"), nullable=True, index=True)
    
    # Informations sur le bien (copie pour historique)
    designation_bien = Column(String(255), nullable=True, comment="Désignation du bien à remplacer")
    prix_acquisition = Column(Float, default=0.0, comment="Prix d'acquisition du bien")
    vnc_actuelle = Column(Float, default=0.0, comment="VNC actuelle du bien")
    
    # Détails de l'ordre
    motif = Column(Text, nullable=False, comment="Motif du remplacement")
    priorite = Column(SQLEnum(PrioriteOrdre), default=PrioriteOrdre.NORMALE, comment="Priorité de l'ordre")
    statut = Column(SQLEnum(StatutOrdreRemplacement), default=StatutOrdreRemplacement.EN_ATTENTE, comment="Statut de l'ordre")
    
    # Dates importantes
    date_creation = Column(DateTime, default=datetime.utcnow, nullable=False)
    date_echeance = Column(DateTime, nullable=True, comment="Date d'échéance pour le remplacement")
    date_validation = Column(DateTime, nullable=True)
    date_execution = Column(DateTime, nullable=True)
    date_rejet = Column(DateTime, nullable=True)
    date_annulation = Column(DateTime, nullable=True)
    
    # Utilisateurs associés
    cree_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    valide_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    execute_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    rejete_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    annule_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True)
    
    # Observations et motifs
    observations = Column(Text, nullable=True, comment="Observations sur le traitement")
    motif_rejet = Column(Text, nullable=True, comment="Motif du rejet")
    motif_annulation = Column(Text, nullable=True, comment="Motif de l'annulation")
    
    # Métadonnées
    metadonnees = Column(Text, nullable=True, comment="Métadonnées supplémentaires (JSON)")
    
    # Relations
    bien = relationship("Bien", foreign_keys=[bien_id], backref="ordres_remplacement")
    bien_remplacement = relationship("Bien", foreign_keys=[bien_remplacement_id], backref="ordres_remplacement_remplacant")
    alerte_vnc = relationship("AlerteVNC", foreign_keys=[alerte_vnc_id], backref="ordres_remplacement")
    
    cree_par = relationship("Utilisateur", foreign_keys=[cree_par_id], backref="ordres_remplacement_crees")
    valide_par = relationship("Utilisateur", foreign_keys=[valide_par_id], backref="ordres_remplacement_valides")
    execute_par = relationship("Utilisateur", foreign_keys=[execute_par_id], backref="ordres_remplacement_executes")
    rejete_par = relationship("Utilisateur", foreign_keys=[rejete_par_id], backref="ordres_remplacement_rejetes")
    annule_par = relationship("Utilisateur", foreign_keys=[annule_par_id], backref="ordres_remplacement_annules")
    
    def __repr__(self):
        return f"<OrdreRemplacement {self.id} - Bien {self.bien_id} - {self.statut.value}>"
    
    @property
    def est_en_retard(self) -> bool:
        """Vérifie si l'ordre est en retard"""
        if self.date_echeance and self.statut in [StatutOrdreRemplacement.EN_ATTENTE, StatutOrdreRemplacement.EN_COURS]:
            return datetime.utcnow() > self.date_echeance
        return False
    
    @property
    def jours_retard(self) -> int:
        """Nombre de jours de retard"""
        if self.est_en_retard:
            return (datetime.utcnow() - self.date_echeance).days
        return 0
    
    @property
    def duree_traitement(self) -> int:
        """Durée de traitement en jours"""
        if self.date_execution and self.date_creation:
            return (self.date_execution - self.date_creation).days
        return 0
    
    @property
    def est_urgent(self) -> bool:
        """Vérifie si l'ordre est urgent ou critique"""
        return self.priorite in [PrioriteOrdre.CRITIQUE, PrioriteOrdre.URGENT]