# backend/app/services/composantisation_service.py
# -*- coding: utf-8 -*-
"""
ComposantisationService — Composantisation OHADA
Phase 4 — Distinguer charge d'entretien vs composant capitalisable

⚠️ PHASE 5 VAGUE 4 (5.20.f) — Corrections multi-tenant :
- Injection de `organisation_id` sur les Composant et JournalEvenementImmobilisation créés
- Vérification d'accès ONG sur les Biens chargés
- Filtrage ONG optionnel sur la liste des composants
"""
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
import logging
import re

from ..models.bien import Bien
from ..models.composant import Composant
from ..models.utilisateur import Utilisateur
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

    # ═══════════════════════════════════════════════════════════════
    # ═══ AJOUT 5.20.f — Helpers multi-tenant                       ═══
    # ═══════════════════════════════════════════════════════════════

    def _is_platform_admin(self, user: Optional[Utilisateur]) -> bool:
        """Retourne True si l'utilisateur est ADMIN plateforme."""
        if not user:
            return False
        return bool(getattr(user, "is_platform_admin", False))

    def _get_organisation_id_bien(self, bien_id: int) -> Optional[int]:
        """Retourne l'organisation_id d'un Bien (None si introuvable)."""
        if bien_id is None:
            return None
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        return getattr(bien, "organisation_id", None) if bien else None

    def _check_acces_bien(
        self,
        current_user: Utilisateur,
        bien: Bien,
        label: str = "bien",
    ) -> None:
        """
        Vérifie l'accès d'un utilisateur à un Bien.
        - ADMIN plateforme → accès total
        - Sinon : le bien doit appartenir à la même ONG
        - Bien sans organisation_id → refusé (donnée historique)
        """
        if self._is_platform_admin(current_user):
            return

        bien_org = getattr(bien, "organisation_id", None)
        bien_id = getattr(bien, "id_bien", "?")

        if bien_org is None:
            raise ValueError(
                f"Accès refusé : {label} #{bien_id} sans organisation "
                f"(donnée historique). Contactez l'administrateur plateforme."
            )

        if bien_org != getattr(current_user, "organisation_id", None):
            raise ValueError(
                f"Accès refusé : {label} #{bien_id} appartient à une autre organisation."
            )

    def _inject_organisation_si_colonne(
        self,
        instance,
        organisation_id: Optional[int],
    ) -> None:
        """
        Injecte `organisation_id` sur une instance SQLAlchemy UNIQUEMENT
        si la classe du modèle possède cette colonne.
        """
        if organisation_id is None:
            return
        try:
            if hasattr(type(instance), "organisation_id"):
                setattr(instance, "organisation_id", organisation_id)
        except Exception as e:
            logger.warning(
                f"Impossible d'injecter organisation_id sur "
                f"{type(instance).__name__} : {e}"
            )

    # ═══ FIN AJOUT 5.20.f ═══

    # ============================================================
    # 1. ANALYSE
    # ============================================================

    def analyser_charge_ou_composant(
        self,
        bien_id: int,
        montant: float,
        description: str,
        current_user: Utilisateur,   # ═══ AJOUT 5.20.f — obligatoire ═══
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

        # ═══ AJOUT 5.20.f — Vérification d'accès ONG ═══
        self._check_acces_bien(current_user, bien)
        # ═══ FIN AJOUT 5.20.f ═══

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
        current_user: Utilisateur,        # ═══ AJOUT 5.20.f — obligatoire ═══
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

        # ═══ AJOUT 5.20.f — Vérification d'accès ONG ═══
        self._check_acces_bien(current_user, bien)

        org_id = getattr(bien, "organisation_id", None)
        user_id = getattr(current_user, "id", None)
        # ═══ FIN AJOUT 5.20.f ═══

        composant = Composant(
            id_bien=bien_id,
            designation=designation,
            numero_serie=None,
            prix_achat=Decimal(str(montant)),
            valeur=montant,
            duree_vie_ans=duree_vie_ans,
            date_mise_en_service=datetime.utcnow(),
        )
        # ═══ AJOUT 5.20.f — Injection organisation_id ═══
        self._inject_organisation_si_colonne(composant, org_id)
        # ═══ FIN AJOUT 5.20.f ═══
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
            # ═══ AJOUT 5.20.f — Injection organisation_id ═══
            self._inject_organisation_si_colonne(journal, org_id)
            # ═══ FIN AJOUT 5.20.f ═══
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
                        "organisation_id": org_id,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit capitalisation échoué : {e}")

        logger.info(
            f"Composant capitalisé sur bien #{bien_id} : {designation} "
            f"({montant} USD) [org={org_id}]"
        )
        return composant

    # ============================================================
    # 3. SORTIE DE L'ANCIEN COMPOSANT
    # ============================================================

    def sortir_ancien_composant(
        self,
        composant_id: int,
        motif: str,
        current_user: Utilisateur,        # ═══ AJOUT 5.20.f — obligatoire ═══
    ) -> Dict[str, Any]:
        """
        Met au rebut un ancien composant (remplacé) :
        - Désactive le composant
        - Génère un événement de sortie dans le journal
        """
        composant = self.db.query(Composant).filter(
            Composant.id_composant == composant_id
        ).first()
        if not composant:
            raise ValueError(f"Composant #{composant_id} introuvable")

        # ═══ AJOUT 5.20.f — Vérification d'accès via le Bien ═══
        bien = self.db.query(Bien).filter(
            Bien.id_bien == composant.id_bien
        ).first()
        if bien:
            self._check_acces_bien(current_user, bien)

        org_id = getattr(bien, "organisation_id", None) if bien else None
        user_id = getattr(current_user, "id", None)
        # ═══ FIN AJOUT 5.20.f ═══

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
            # ═══ AJOUT 5.20.f — Injection organisation_id ═══
            self._inject_organisation_si_colonne(journal, org_id)
            # ═══ FIN AJOUT 5.20.f ═══
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
                        "organisation_id": org_id,
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

    def lister_composants_bien(
        self,
        bien_id: int,
        current_user: Optional[Utilisateur] = None,   # ═══ AJOUT 5.20.f — optionnel ═══
    ) -> List[Composant]:
        """
        Liste les composants d'un bien.
        Si `current_user` est fourni → filtre ONG appliqué (sauf ADMIN plateforme).
        """
        query = self.db.query(Composant).filter(Composant.id_bien == bien_id)

        # ═══ AJOUT 5.20.f — Filtre ONG ═══
        if current_user is not None and not self._is_platform_admin(current_user):
            query = query.join(
                Bien, Bien.id_bien == Composant.id_bien
            ).filter(
                Bien.organisation_id == getattr(current_user, "organisation_id", None)
            )
        # ═══ FIN AJOUT 5.20.f ═══

        return query.all()