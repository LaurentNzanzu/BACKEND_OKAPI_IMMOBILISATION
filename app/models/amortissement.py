from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class MethodeAmortissement(enum.Enum):
    LINEAIRE = "LINEAIRE"
    DEGRESSIF = "DEGRESSIF"
    UNITE_PRODUCTION = "UNITE_PRODUCTION"
    COMPOSANTS = "COMPOSANTS"
    SPECIFIQUE_OKAPI = "SPECIFIQUE_OKAPI"


class StatutAmortissement(enum.Enum):
    EN_COURS = "EN_COURS"
    TERMINE = "TERMINE"
    SUSPENDU = "SUSPENDU"


class Amortissement(Base):
    __tablename__ = "amortissements"
    id_amortissement = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    exercice = Column(Integer, nullable=False)
    methode = Column(SQLEnum(MethodeAmortissement), nullable=False)
    valeur_origine = Column(Float, nullable=False)
    valeur_residuelle = Column(Float, default=0.0)
    duree_vie_comptable_ans = Column(Integer, nullable=False)
    duree_vie_fiscale_ans = Column(Integer, nullable=False)
    taux_comptable = Column(Float, nullable=False)
    taux_fiscal = Column(Float, nullable=False)
    coefficient_deg = Column(Float, nullable=True)
    
    # Champs pour prorata (RDC/SYSCOHADA)
    jours_prorata = Column(Integer, default=360)  # Base 360 jours pour linéaire
    mois_prorata = Column(Integer, nullable=True)  # Mois complets pour dégressif
    date_mise_en_service = Column(DateTime, nullable=True)  # Date réelle de mise en service
    date_acquisition = Column(DateTime, nullable=True)  # Date d'acquisition pour le calcul dégressif
    date_debut = Column(DateTime, nullable=True)  # Date de début pour le calcul linéaire

    
    # Champs pour unités de production
    unites_totales_prevues = Column(Integer, nullable=True)
    unites_consommees_exercice = Column(Integer, nullable=True)
    production_totale_prevue = Column(Integer, nullable=True)
    production_reelle_exercice = Column(Integer, nullable=True)
    
    # Champs pour méthode spécifique OKAPI
    duree_fournisseur = Column(Integer, nullable=True)
    jours_ouvres_mois = Column(Integer, default=26)
    jours_utilisation_annee = Column(Integer, nullable=True)
    
    # Calculs
    annuite_comptable = Column(Float, nullable=False)
    annuite_fiscale = Column(Float, nullable=False)
    ecart_a_reintegrer = Column(Float, nullable=False)
    cumul_comptable = Column(Float, default=0.0)
    cumul_fiscal = Column(Float, default=0.0)
    valeur_nette_comptable = Column(Float)
    valeur_nette_fiscale = Column(Float)
    
    # Dépréciation
    valeur_actualisee = Column(Float, nullable=True)  # Nouvelle valeur après dépréciation
    date_depreciation = Column(DateTime, nullable=True)
    montant_depreciation = Column(Float, default=0.0)
    
    # Dates et statut
    #date_debut = Column(DateTime, nullable=False)
    date_fin_prevue = Column(DateTime)
    statut = Column(SQLEnum(StatutAmortissement), default=StatutAmortissement.EN_COURS)
    date_creation = Column(DateTime, default=datetime.utcnow)

    # Colonnes de verrouillage
    est_verrouille = Column(Boolean, default=False, nullable=False, comment="True si l'amortissement est verrouillé")
    date_verrouillage = Column(DateTime, nullable=True, comment="Date du verrouillage")
    verrouille_par_id = Column(Integer, ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True, comment="Utilisateur ayant verrouillé")
    raison_verrouillage = Column(String(255), nullable=True, comment="Raison du verrouillage (obligatoire)")

    bien = relationship("Bien", back_populates="amortissements")
    ecritures = relationship("EcritureComptable", back_populates="amortissement", cascade="all, delete-orphan")
    verrouille_par = relationship("Utilisateur", foreign_keys=[verrouille_par_id])

    def verrouiller(self, utilisateur_id: int, raison: str):
        """Verrouille définitivement l'amortissement."""
        if self.est_verrouille:
            raise ValueError("Cet amortissement est déjà verrouillé")
        if not raison or not raison.strip():
            raise ValueError("La raison du verrouillage est obligatoire")
        self.est_verrouille = True
        self.date_verrouillage = datetime.utcnow()
        self.verrouille_par_id = utilisateur_id
        self.raison_verrouillage = raison.strip()
        return self

    @property
    def est_modifiable(self) -> bool:
        """Vérifie si l'amortissement peut être modifié."""
        return not self.est_verrouille