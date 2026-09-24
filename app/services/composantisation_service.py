# backend/app/services/composantisation_service.py
# -*- coding: utf-8 -*-
"""
ComposantisationService — Composantisation OHADA
Phase 4 — Distinguer charge d'entretien vs composant capitalisable
"""
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
import logging
import re

from ..models.bien import Bien
from ..models.composant import Composant
from ..models.journal_evenements_immobilisation import (
    JournalEvenementImmobilisation,
    TypeEvenementImmobilisation,
)
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


# Mots-clés qui suggèrent une capitalisation OHADA
MOTS_CAPITALISATION = [
    "moteur", "moteurs", "boîte", "boite", "transmission", "châssis",
    "chassis", "compresseur", "groupe électrogène", "groupe electrogene",
    "installation", "structure", "carrosserie", "aménagement", "amenagement",
    "révision majeure", "revision majeure", "réfection", "refection",
    "remplacement complet", "rénovation lourde", "renovation lourde",
]

# Seuil minimum pour capitaliser (USD)
SEUIL_CAPITALISATION_MIN = 500.0

# Seuil : ratio coût réparation / prix acquisition (au-delà → capitaliser)
SEUIL_RATIO_CAPITALISATION = 0.15  # 15%


class ComposantisationService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)

    # ============================================================
    # 1. ANALYSE
    # ============================================================

    def analyser_charge_ou_composant(
        self,
        bien_id: int,
        montant: float,
        description: str,
    ) -> Dict[str, Any]:
        """
        Détermine si une dépense doit être traitée comme :
        - CHARGE d'entretien (compte 6241)
        - COMPOSANT capitalisable (actif + amortissement OHADA)

        Critères (ordre de priorité) :
        1. Description contient un mot-clé de capitalisation
        2. Montant ≥ SEUIL_CAPITALISATION_MIN
        3. Ratio coût / prix_acquisition ≥ SEUIL_RATIO_CAPITALISATION
        """
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien #{bien_id} introuvable")

        prix_acq = float(bien.prix_acquisition or 0)
        ratio = (montant / prix_acq) if prix_acq > 0 else 0

        # Analyse mot-clé
        desc_lower = (description or "").lower()
        mot_cle_trouve = None
        for mot in MOTS_CAPITALISATION:
            if re.search(r"\b" + re.escape(mot) + r"\b", desc_lower):
                mot_cle_trouve = mot
                break

        est_composant = False
        raison = ""

        if mot_cle_trouve:
            est_composant = True
            raison = f"Mot-clé de capitalisation détecté : '{mot_cle_trouve}'"
        elif montant >= SEUIL_CAPITALISATION_MIN and ratio >= SEUIL_RATIO_CAPITALISATION:
            est_composant = True
            raison = (
                f"Montant important ({montant:.2f}) et ratio significatif "
                f"({ratio*100:.1f}% du prix d'acquisition)"
            )
        else:
            raison = "Traitement en charge d'entretien standard"

        return {
            "bien_id": bien_id,
            "montant": montant,
            "description": description,
            "prix_acquisition": prix_acq,
            "ratio": round(ratio, 4),
            "type_traitement": "COMPOSANT" if est_composant else "CHARGE",
            "raison": raison,
            "mot_cle_detecte": mot_cle_trouve,
            "compte_comptable_suggere": "2445" if est_composant else "6241",
        }

    # ============================================================
    # 2. CAPITALISATION
    # ============================================================

    def capitaliser_composant(
        self,
        bien_id: int,
        montant: float,
        designation: str,
        duree_vie_ans: int,
        user_id: Optional[int] = None,
        reference_piece: Optional[str] = None,
    ) -> Composant:
        """
        Crée un nouveau composant amortissable rattaché au bien.
        Génère un événement dans le journal des immobilisations.
        """
        if montant <= 0:
            raise ValueError("Le montant doit être strictement positif")
        if duree_vie_ans <= 0:
            raise ValueError("La durée de vie doit être strictement positive")

        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien #{bien_id} introuvable")

        composant = Composant(
            id_bien=bien_id,
            designation=designation,
            numero_serie=None,
            prix_achat=Decimal(str(montant)),
            valeur=montant,
            duree_vie_ans=duree_vie_ans,
            date_mise_en_service=datetime.utcnow(),
        )
        self.db.add(composant)
        self.db.flush()

        # Journal des immobilisations
        try:
            journal = JournalEvenementImmobilisation(
                bien_id=bien_id,
                type_evenement=TypeEvenementImmobilisation.ACQUISITION,
                date_evenement=datetime.utcnow(),
                libelle=f"Capitalisation composant : {designation}",
                montant=montant,
                reference_piece=reference_piece,
                utilisateur_id=user_id,
                metadonnees=f"Durée amortissement : {duree_vie_ans} ans",
            )
            self.db.add(journal)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Erreur journalisation composant (non bloquante) : {e}")

        if user_id:
            try:
                self.audit_service.log_create(
                    user_id=user_id,
                    table_name="composants",
                    record_id=composant.id_composant,
                    new_values={
                        "bien_id": bien_id,
                        "designation": designation,
                        "montant": montant,
                        "duree_vie_ans": duree_vie_ans,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit capitalisation échoué : {e}")

        logger.info(f"Composant capitalisé sur bien #{bien_id} : {designation} ({montant} USD)")
        return composant

    # ============================================================
    # 3. SORTIE DE L'ANCIEN COMPOSANT
    # ============================================================

    def sortir_ancien_composant(
        self,
        composant_id: int,
        motif: str,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Met au rebut un ancien composant (remplacé) :
        - Désactive le composant
        - Génère un événement de sortie dans le journal
        """
        composant = self.db.query(Composant).filter(Composant.id_composant == composant_id).first()
        if not composant:
            raise ValueError(f"Composant #{composant_id} introuvable")

        # Marquer comme réformé (si le champ existe)
        if hasattr(composant, "est_actif"):
            composant.est_actif = False

        valeur_vnc = float(composant.valeur or 0)

        try:
            journal = JournalEvenementImmobilisation(
                bien_id=composant.id_bien,
                type_evenement=TypeEvenementImmobilisation.SORTIE_REBUT,
                date_evenement=datetime.utcnow(),
                libelle=f"Sortie composant : {composant.designation} — {motif}",
                montant=valeur_vnc,
                utilisateur_id=user_id,
            )
            self.db.add(journal)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Erreur journalisation sortie composant : {e}")

        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="composants",
                    record_id=composant_id,
                    action="SORTIE_COMPOSANT",
                    nouvelles_valeurs={
                        "bien_id": composant.id_bien,
                        "designation": composant.designation,
                        "motif": motif,
                        "vnc": valeur_vnc,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit sortie composant échoué : {e}")

        return {
            "composant_id": composant_id,
            "bien_id": composant.id_bien,
            "valeur_vnc": valeur_vnc,
            "motif": motif,
        }

    # ============================================================
    # 4. UTILITAIRES
    # ============================================================

    def lister_composants_bien(self, bien_id: int) -> List[Composant]:
        return self.db.query(Composant).filter(Composant.id_bien == bien_id).all()