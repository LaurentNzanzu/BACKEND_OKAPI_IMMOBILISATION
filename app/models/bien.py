# backend/app/models/bien.py
from sqlalchemy import Column, Integer, String, Date, DateTime, Enum, Numeric, ForeignKey, Text, Boolean, Float, event
from sqlalchemy.orm import relationship, validates
from datetime import datetime
from decimal import Decimal
import enum
from ..core.database import Base

class EtatBien(enum.Enum):
    NEUF = "NEUF"
    BON = "BON"
    USAGE = "USAGE"
    PANNE = "PANNE"
    REFORME = "REFORME"
    MAINTENANCE = "MAINTENANCE"
    EN_TEST = "EN_TEST"

class StatutComptable(str, enum.Enum):
    ACTIF = "ACTIF"
    EN_AMORTISSEMENT = "EN_AMORTISSEMENT"
    EN_DEPRECIATION = "EN_DEPRECIATION"
    EN_COURS_CESSION = "EN_COURS_CESSION"
    CEDE = "CEDE"
    MIS_AU_REBUT = "MIS_AU_REBUT"
    EN_REPARATION = "EN_REPARATION"
    HORS_SERVICE = "HORS_SERVICE"

class Bien(Base):
    __tablename__ = "biens"
    
    id_bien = Column(Integer, primary_key=True, index=True)
    qr_code = Column(String(100), unique=True, index=True)
    date_acquisition = Column(Date)
    prix_acquisition = Column(Numeric(10, 2))
    etat = Column(Enum(EtatBien), default=EtatBien.NEUF)
    id_localisation = Column(Integer, ForeignKey('localisations.id_localisation'), nullable=False)
    date_fin_garantie = Column(Date, nullable=True)
    description = Column(String(500))
    image = Column(String(500))
    date_creation = Column(DateTime, default=datetime.utcnow)
    
    # ✅ AJOUT DE LA COLONNE MANQUANTE
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    date_sortie = Column(DateTime, nullable=True)
    date_retour = Column(DateTime, nullable=True)

    # Statut comptable (String en base pour compatibilité, validé par Enum)
    statut_comptable = Column(String(50), default=StatutComptable.ACTIF.value)

    cumul_amortissement = Column(Numeric(15, 2), default=0)
    cumul_depreciation = Column(Numeric(15, 2), default=0)

    # === CHAMPS PHASE 1 & 3 ===
    mode_paiement = Column(String(20), default="credit", nullable=False)
    fournisseur_id = Column(Integer, ForeignKey("fournisseurs.id", ondelete="SET NULL"), nullable=True)
    est_critique = Column(Boolean, default=False, nullable=False, comment="True si le bien est critique")
    
    # === MODIFIÉ PHASE 1.5 ===
    score_fiabilite = Column(Numeric(5, 2), nullable=True, comment="Score de fiabilité sur 100")
    date_dernier_calcul_score = Column(DateTime, comment="Date du dernier calcul du score")
    
    # === NOUVEAUX ATTRIBUTS PHASE 1.5 ===
    score_a_recalculer = Column(Boolean, default=False, 
                                 comment="True si une panne/maintenance a invalidé le score")
    nombre_pannes_historique = Column(Integer, default=0)
    cout_total_maintenance = Column(Numeric(15, 2), default=0)

    vnc_alerte_declenchee = Column(Boolean, default=False, comment="True si alerte VNC déclenchée")
    seuil_alerte_atteint = Column(String(20), default=None, comment="Seuil d'alerte VNC atteint")

    # === NOUVEAU CHAMP PHASE 1.4 ===
    id_cession_validee = Column(Integer, ForeignKey('cessions.id_cession', ondelete="SET NULL"), nullable=True)

    # Discriminator pour l'héritage (Phase 2)
    type_bien = Column(String(50))

    __mapper_args__ = {
        "polymorphic_identity": "bien",
        "polymorphic_on": type_bien
    }

    # =========================================================================
    # RELATIONS
    # =========================================================================
    
    amortissements = relationship("Amortissement", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    pannes = relationship("Panne", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    composants = relationship("Composant", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    maintenances = relationship("Maintenance", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    ecritures_comptables = relationship("EcritureComptable", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    mouvements = relationship("MouvementBien", back_populates="bien", cascade="all, delete-orphan", lazy="dynamic")

    actif_remplacement_id = Column(Integer, ForeignKey('biens.id_bien', ondelete="SET NULL"), nullable=True, index=True)
    actif_remplacement = relationship("Bien", foreign_keys=[actif_remplacement_id], remote_side=[id_bien], backref="actif_remplace")

    decisions_ia = relationship("DecisionIA", back_populates="bien", cascade="all, delete-orphan")
    fournisseur = relationship("Fournisseur", back_populates="biens", foreign_keys=[fournisseur_id])
    localisation_ref = relationship("Localisation", back_populates="biens")

    journal_events = relationship("JournalEvenementImmobilisation", foreign_keys="JournalEvenementImmobilisation.bien_id", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    events_as_remplace = relationship("JournalEvenementImmobilisation", foreign_keys="JournalEvenementImmobilisation.bien_remplace_id", lazy="select")
    events_as_nouveau = relationship("JournalEvenementImmobilisation", foreign_keys="JournalEvenementImmobilisation.bien_nouveau_id", lazy="select")

    alertes_vnc = relationship("AlerteVNC", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    projections = relationship("ProjectionInvestissement", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    cessions = relationship("Cession", foreign_keys="Cession.id_bien", back_populates="bien", cascade="all, delete-orphan", lazy="select")
    validations = relationship("Validation", back_populates="bien", cascade="all, delete-orphan", lazy="select")

    # NOUVELLE RELATION PHASE 1.4
    cession_validee = relationship("Cession", foreign_keys=[id_cession_validee])

    # =========================================================================
    # PROPRIÉTÉS
    # =========================================================================

    @property
    def valeur_nette_comptable(self):
        """Calcule la valeur nette comptable du bien."""
        return float(self.prix_acquisition or 0) - float(self.cumul_amortissement or 0)

    @property
    def ratio_vnc_restante(self):
        """Calcule le ratio VNC restante par rapport à la valeur d'origine."""
        if self.prix_acquisition and self.prix_acquisition > 0:
            return self.valeur_nette_comptable / float(self.prix_acquisition)
        return 0.0

    # =========================================================================
    # MÉTHODES MÉTIER & TRANSITIONS DE STATUT
    # =========================================================================

    @validates('statut_comptable')
    def validate_statut(self, key, statut):
        """Validation basique du statut comptable pour éviter les valeurs arbitraires."""
        if statut and statut not in [s.value for s in StatutComptable]:
            raise ValueError(f"Statut comptable invalide: {statut}")
        return statut

    def calcul_age(self) -> int:
        """Calcule l'âge du bien en années."""
        from datetime import date
        return date.today().year - self.date_acquisition.year

    def changer_etat(self, nouvel_etat: EtatBien):
        """Change l'état physique du bien."""
        self.etat = nouvel_etat

    def est_en_panne(self) -> bool:
        """Vérifie si le bien est en panne."""
        return self.etat == EtatBien.PANNE

    def mettre_a_jour_score(self, nouveau_score: float):
        """Met à jour le score de fiabilité."""
        self.score_fiabilite = nouveau_score
        self.date_dernier_calcul_score = datetime.utcnow()

    # --- MÉTHODES DE CESSION (PHASE 1.4) ---

    def initier_cession(self, cession_id: int):
        """
        Passe le bien en statut EN_COURS_CESSION lors de la création de la cession.
        Bloque toute autre modification de statut pendant le workflow.
        """
        statuts_bloques = [
            StatutComptable.CEDE.value, 
            StatutComptable.HORS_SERVICE.value, 
            StatutComptable.MIS_AU_REBUT.value,
            StatutComptable.EN_COURS_CESSION.value
        ]
        if self.statut_comptable in statuts_bloques:
            raise ValueError(f"Impossible d'initier une cession pour un bien au statut {self.statut_comptable}")
        
        self.statut_comptable = StatutComptable.EN_COURS_CESSION.value
        self.id_cession_validee = cession_id
        return self

    def ceder(self, cession_id: int, date_sortie: datetime = None):
        """
        Transition contrôlée vers le statut CEDE.
        NE DOIT être appelée que par le service de validation après 
        confirmation de l'encaissement par le caissier.
        """
        if self.statut_comptable == StatutComptable.CEDE.value:
            raise ValueError("Ce bien est déjà cédé.")
        
        if self.statut_comptable == StatutComptable.EN_COURS_CESSION.value:
            if self.id_cession_validee != cession_id:
                raise ValueError("La cession spécifiée ne correspond pas à la cession en cours.")
        else:
            raise ValueError(f"Transition invalide : {self.statut_comptable} -> CEDE. Le bien doit d'abord être en EN_COURS_CESSION.")
        
        self.statut_comptable = StatutComptable.CEDE.value
        self.date_sortie = date_sortie or datetime.utcnow()
        self.id_cession_validee = cession_id
        
        return self 

    def annuler_cession(self):
        """
        Annule le processus de cession et retourne le bien à ACTIF.
        """
        if self.statut_comptable != StatutComptable.EN_COURS_CESSION.value:
            raise ValueError("Aucune cession en cours à annuler.")
        
        self.statut_comptable = StatutComptable.ACTIF.value
        self.id_cession_validee = None
        return self

    # =========================================================================
    # SCORE DE FIABILITÉ (PHASE 1.5)
    # =========================================================================

    def calculer_score_fiabilite(self, force: bool = False) -> Decimal:
        """
        Calcule le score de fiabilité basé sur l'historique des pannes et maintenances.
        
        Formule :
        - Base : 100 points
        - Pénalité pannes : -15 points par panne (max -60)
        - Pénalité coût : -1 point par tranche de 100 000 FCFA de maintenance (max -30)
        - Pénalité âge : -2 points par année d'âge (max -20)
        
        Le score est borné entre 0 et 100.
        
        Args:
            force: Force le recalcul même si score_a_recalculer est False
            
        Returns:
            Decimal: Score calculé (0-100)
        """
        if not force and not self.score_a_recalculer and self.score_fiabilite is not None:
            return Decimal(str(self.score_fiabilite))
        
        # Récupérer les données nécessaires
        nb_pannes = self.nombre_pannes_historique or 0
        cout_total = self.cout_total_maintenance or Decimal('0')
        age = self.calcul_age() or 0  # Méthode existante
        
        # Calcul des composantes
        score = Decimal('100')
        
        # Pénalité pannes
        penalite_pannes = min(nb_pannes * 15, 60)
        score -= Decimal(str(penalite_pannes))
        
        # Pénalité coût (par tranche de 100 000)
        penalite_cout = min(float(cout_total) / 100000, 30)
        score -= Decimal(str(penalite_cout))
        
        # Pénalité âge
        penalite_age = min(age * 2, 20)
        score -= Decimal(str(penalite_age))
        
        # Bornage
        score = max(Decimal('0'), min(Decimal('100'), score))
        
        # Arrondi à 2 décimales
        score = score.quantize(Decimal('0.01'))
        
        # Mise à jour des attributs
        self.score_fiabilite = score
        self.date_dernier_calcul_score = datetime.utcnow()
        self.score_a_recalculer = False
        
        return score

    def declarer_panne(self, cout_reparation: Decimal = None, 
                       description: str = None, 
                       date_panne: datetime = None):
        """
        Déclare une panne sur le bien et invalide le score pour recalcul asynchrone.
        
        Args:
            cout_reparation: Coût estimé ou réel de la réparation
            description: Description de la panne
            date_panne: Date de la panne (défaut: maintenant)
        """
        self.nombre_pannes_historique = (self.nombre_pannes_historique or 0) + 1
        
        if cout_reparation:
            if not isinstance(cout_reparation, Decimal):
                cout_reparation = Decimal(str(cout_reparation))
            self.cout_total_maintenance = (self.cout_total_maintenance or Decimal('0')) + cout_reparation
        
        self.score_a_recalculer = True
        # NE PAS recalculer ici — laisser la tâche asynchrone faire le travail
        
        return self

    def invalider_score(self):
        """Marque le score comme nécessitant un recalcul."""
        self.score_a_recalculer = True
        return self
    
    def est_score_obsolete(self, delai_max_jours: int = 30) -> bool:
        """
        Vérifie si le score doit être recalculé (panne déclarée ou délai dépassé).
        """
        if self.score_a_recalculer:
            return True
        if self.date_dernier_calcul_score is None:
            return True
        delai = datetime.utcnow() - self.date_dernier_calcul_score
        return delai.days > delai_max_jours

# =========================================================================
# ÉCOUTEURS SQLALCHEMY (SÉCURISATION AVANT PERSISTANCE)
# =========================================================================

@event.listens_for(Bien, 'before_update')
def _bien_avant_mise_a_jour(mapper, connection, target):
    """
    Sécurise la persistance : empêche de sauvegarder un bien avec le statut CEDE 
    si aucune cession validée n'est associée.
    """
    if target.statut_comptable == StatutComptable.CEDE.value:
        if not target.id_cession_validee:
            raise ValueError("Impossible de passer le statut à CEDE sans une cession validée associée (id_cession_validee manquant).")