# backend/app/models/ecriture_comptable.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Enum as SQLEnum, Numeric, event
from sqlalchemy.orm import relationship, validates
from datetime import datetime
from decimal import Decimal
from ..core.database import Base
import enum

class TypeOperationEnum(enum.Enum):
    DOTATION_AMORTISSEMENT = "DOTATION_AMORTISSEMENT"
    ACQUISITION = "ACQUISITION"
    CESSION = "CESSION"
    REPRISE = "REPRISE"
    REPRISE_DEPRECIATION = "REPRISE_DEPRECIATION"
    DEPRECIATION = "DEPRECIATION"
    DECAISSEMENT = "DECAISSEMENT"

class StatutEcriture(enum.Enum):
    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"
    REJETEE = "REJETEE"
    MODIFIEE = "MODIFIEE"
    EN_ATTENTE_PAIEMENT = "EN_ATTENTE_PAIEMENT"

class EcritureComptable(Base):
    __tablename__ = "ecritures_comptables"
    
    id_ecriture = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien", ondelete="CASCADE"), nullable=False)
    id_amortissement = Column(Integer, ForeignKey("amortissements.id_amortissement"), nullable=True)
    # === NOUVEAU CHAMP PHASE 2 ===
    id_validation = Column(Integer, ForeignKey("validations.id_validation", ondelete="SET NULL"), nullable=True)

    date_ecriture = Column(DateTime, nullable=False, default=datetime.utcnow)
    exercice = Column(Integer, nullable=False)
    type_operation = Column(SQLEnum(TypeOperationEnum), nullable=False)
    statut = Column(SQLEnum(StatutEcriture), default=StatutEcriture.BROUILLON)
    libelle = Column(Text)
    
    compte_debit = Column(String(20), nullable=False)
    compte_credit = Column(String(20), nullable=False)
    montant = Column(Numeric(15, 2), nullable=False)  # Changé Float -> Numeric
    montant_original = Column(Numeric(15, 2), nullable=True)
    
    motif_modification = Column(Text, nullable=True)
    details_calcul = Column(Text, nullable=True)
    piece_justificative = Column(String(100))
    journal = Column(String(20), nullable=True)
    periode_comptable = Column(String(7), nullable=True)
    reference_id = Column(Integer, nullable=True)
    validee = Column(Boolean, default=False)
    
    date_creation = Column(DateTime, default=datetime.utcnow)
    cree_par = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    date_validation = Column(DateTime)
    valide_par = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    id_validateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    id_modificateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=True)
    date_modification = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    # Relations
    bien = relationship("Bien", back_populates="ecritures_comptables")
    amortissement = relationship("Amortissement", back_populates="ecritures")
    # === NOUVELLE RELATION ===
    validation = relationship("Validation", back_populates="ecritures_comptables")
    
    createur = relationship("Utilisateur", foreign_keys=[cree_par])
    validateur = relationship("Utilisateur", foreign_keys=[id_validateur])
    validateur_par = relationship("Utilisateur", foreign_keys=[valide_par])
    modificateur = relationship("Utilisateur", foreign_keys=[id_modificateur])

    # =========================================================================
    # VALIDATIONS MÉTIER (SYSCOHADA)
    # =========================================================================

    @validates('montant')
    def validate_montant(self, key, montant):
        """
        Valide que le montant est strictement positif.
        """
        if montant is not None and montant <= 0:
            raise ValueError("Le montant d'une écriture comptable doit être strictement positif.")
        return montant

    @validates('compte_debit', 'compte_credit')
    def validate_comptes(self, key, compte):
        """
        Valide que les comptes comptables ne sont pas vides.
        """
        if compte is not None and (not isinstance(compte, str) or not compte.strip()):
            raise ValueError(f"Le {key} ne peut pas être vide.")
        return compte.strip()

    def verifier_equilibre(self):
        """
        Vérifie que l'écriture est équilibrée et conforme aux règles SYSCOHADA.
        
        Pour une écriture simple (1 compte débit, 1 compte crédit), l'équilibre 
        est garanti par le fait qu'un seul montant est stocké et doit être > 0.
        Pour les écritures complexes, cette méthode servira de point d'extension.
        
        Returns:
            bool: True si l'écriture est valide.
            
        Raises:
            ValueError: Si le montant est invalide, nul, négatif, ou si les comptes sont manquants.
        """
        if self.montant is None:
            raise ValueError("Le montant est requis pour vérifier l'équilibre comptable.")
        if self.montant <= 0:
            raise ValueError("Le montant doit être strictement positif.")
        if not self.compte_debit or not self.compte_credit:
            raise ValueError("Les comptes débit et crédit sont obligatoires.")
            
        # L'équilibre est intrinsèque pour une écriture simple à montant unique.
        return True

    @classmethod
    def creer_ecriture_equilibree(cls, compte_debit: str, compte_credit: str, 
                                  montant: Decimal, type_operation: TypeOperationEnum, **kwargs):
        """
        Factory method garantissant la création d'une écriture comptable équilibrée.
        Applique les validations métiers avant instanciation et retourne une instance prête à être persistée.
        
        Args:
            compte_debit (str): Code du compte à débiter.
            compte_credit (str): Code du compte à créditer.
            montant (Decimal): Montant strictement positif.
            type_operation (TypeOperationEnum): Nature de l'opération comptable.
            **kwargs: Autres arguments passés au constructeur (ex: libelle, exercice, etc.)
            
        Returns:
            EcritureComptable: Instance validée et équilibrée.
        """
        if not isinstance(montant, Decimal):
            montant = Decimal(str(montant))
        if montant <= 0:
            raise ValueError("Le montant doit être strictement positif.")
        if not compte_debit or not compte_credit:
            raise ValueError("Les comptes débit et crédit sont obligatoires.")

        ecriture = cls(
            compte_debit=compte_debit.strip(),
            compte_credit=compte_credit.strip(),
            montant=montant,
            type_operation=type_operation,
            **kwargs
        )
        ecriture.verifier_equilibre()
        return ecriture

# =========================================================================
# ÉCOUTEURS SQLALCHEMY (BLOQUAGE AVANT PERSISTANCE)
# =========================================================================

@event.listens_for(EcritureComptable, "before_insert")
@event.listens_for(EcritureComptable, "before_update")
def _ecriture_comptable_avant_persistance(mapper, connection, target):
    """
    Événement SQLAlchemy garantissant qu'aucune écriture déséquilibrée 
    ne peut être insérée ou mise à jour en base de données.
    """
    target.verifier_equilibre()