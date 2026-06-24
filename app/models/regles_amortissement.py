from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class RegleAmortissement(Base):
    """Table de configuration dynamique des règles d'amortissement (RDC/SYSCOHADA)"""
    __tablename__ = "regles_amortissement"
    
    id_regle = Column(Integer, primary_key=True, index=True)
    categorie_bien = Column(String(50), nullable=False, unique=True)  # vehicule, machine, ordinateur, mobilier, etc.
    
    # Durées de vie par défaut
    duree_vie_ans = Column(Integer, nullable=False)
    
    # Taux fiscal par défaut
    taux_fiscal = Column(Float, nullable=False)
    
    # Coefficients dégressifs par durée
    coeff_deg_3_4_ans = Column(Float, default=1.5)
    coeff_deg_5_6_ans = Column(Float, default=2.0)
    coeff_deg_7_plus_ans = Column(Float, default=2.5)
    
    # Comptes comptables
    compte_dotation = Column(String(20), default="6812")  # Dotations aux amortissements
    compte_amortissement = Column(String(20), nullable=True)  # Compte d'amortissement (28xxx)
    compte_depreciation = Column(String(20), default="2944")  # Compte OHADA dépréciation
    
    # Base de calcul
    base_jours_annee = Column(Integer, default=360)  # SYSCOHADA: 360 jours
    prorata_debut_mois = Column(Boolean, default=True)  # Dégressif: début mois
    
    # Actif
    est_active = Column(Boolean, default=True)
    date_modification = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    modifie_par = Column(String(100), nullable=True)
    
    def __repr__(self):
        return f"<RegleAmortissement(categorie='{self.categorie_bien}', duree={self.duree_vie_ans}ans, taux={self.taux_fiscal}%)>"


class RegleHistorique(Base):
    """Historique des modifications des règles"""
    __tablename__ = "regles_historique"
    
    id_historique = Column(Integer, primary_key=True, index=True)
    id_regle = Column(Integer, nullable=False)
    categorie_bien = Column(String(50))
    ancienne_valeur = Column(String(500))
    nouvelle_valeur = Column(String(500))
    champ_modifie = Column(String(100))
    date_modification = Column(DateTime, default=datetime.utcnow)
    modifie_par = Column(String(100))