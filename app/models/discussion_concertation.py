# app/models/discussion_concertation.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base
import enum


class TypeValidationEnum(str, enum.Enum):
    CESSION = "CESSION"
    REBUT = "REBUT"


class DecisionValidationConcertation(str, enum.Enum):
    """Décisions possibles pour la validation de concertation"""
    APPROUVE = "APPROUVE"
    REJETE = "REJETE"
    EN_ATTENTE = "EN_ATTENTE"


class DiscussionConcertation(Base):
    """Table des discussions de concertation pour les validations doubles (DG + Comptable)"""
    __tablename__ = "discussions_concertation"

    id = Column(Integer, primary_key=True, index=True)
    id_bien = Column(Integer, ForeignKey("biens.id_bien"), nullable=False)
    type_validation = Column(SQLEnum(TypeValidationEnum), nullable=False)
    titre = Column(String(255), nullable=False)
    est_active = Column(Boolean, default=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    date_cloture = Column(DateTime, nullable=True)

    # Relations
    bien = relationship("Bien")
    messages = relationship("MessageConcertation", back_populates="discussion", cascade="all, delete-orphan")
    validations = relationship("ValidationConcertation", back_populates="discussion", cascade="all, delete-orphan")


class MessageConcertation(Base):
    """Messages échangés dans une discussion"""
    __tablename__ = "messages_concertation"

    id = Column(Integer, primary_key=True, index=True)
    id_discussion = Column(Integer, ForeignKey("discussions_concertation.id"), nullable=False)
    id_utilisateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)
    contenu = Column(Text, nullable=False)
    parent_id = Column(Integer, ForeignKey("messages_concertation.id"), nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    est_modifie = Column(Boolean, default=False)
    date_modification = Column(DateTime, nullable=True)

    # Relations
    discussion = relationship("DiscussionConcertation", back_populates="messages")
    utilisateur = relationship("Utilisateur")
    reponses = relationship("MessageConcertation", backref="parent", remote_side=[id])


class ValidationConcertation(Base):
    """Validations individuelles du DG et du Comptable"""
    __tablename__ = "validations_concertation"

    id = Column(Integer, primary_key=True, index=True)
    id_discussion = Column(Integer, ForeignKey("discussions_concertation.id"), nullable=False)
    id_validateur = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)
    decision = Column(SQLEnum(DecisionValidationConcertation), nullable=False)
    commentaire = Column(Text, nullable=True)
    date_decision = Column(DateTime, default=datetime.utcnow)

    # Relations
    discussion = relationship("DiscussionConcertation", back_populates="validations")
    validateur = relationship("Utilisateur")