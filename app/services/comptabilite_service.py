# app/services/comptabilite_service.py
from decimal import Decimal
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..models.ecriture_comptable import EcritureComptable, TypeOperationEnum, StatutEcriture
from ..models.amortissement import Amortissement, StatutAmortissement
from ..models.regles_amortissement import RegleAmortissement
from ..models.bien import Bien
from ..models.cession import Cession
from ..schemas.cession import CessionCreate, RebutCreate
from ..schemas.ecriture_comptable import EcritureCreate

import logging

logger = logging.getLogger(__name__)


class ComptabiliteService:
    def __init__(self, db: Session, cree_par_id: Optional[int] = None):
        self.db = db
        self.cree_par_id = cree_par_id

    def _journal_pour_type(self, type_operation: TypeOperationEnum) -> str:
        """Détermine le journal comptable pour un type d'opération."""
        mapping = {
            TypeOperationEnum.ACQUISITION: "ACH",
            TypeOperationEnum.DOTATION_AMORTISSEMENT: "OD",
            TypeOperationEnum.DEPRECIATION: "OD",
            TypeOperationEnum.REPRISE_DEPRECIATION: "OD",
            TypeOperationEnum.CESSION: "OD",
            TypeOperationEnum.REPRISE: "OD",
        }
        return mapping.get(type_operation, "OD")

    def _round(self, value: float) -> float:
        """Arrondit une valeur à 2 décimales."""
        return float(Decimal(str(value)).quantize(Decimal('0.01')))

    # ============================================================
    # 🔐 VÉRIFICATION DE L'ÉQUILIBRE COMPTABLE
    # ============================================================

    def _verifier_equilibre(self, ecritures: List[EcritureComptable]) -> bool:
        """
        Vérifie que la somme des débits égale la somme des crédits.
        
        Args:
            ecritures: Liste d'écritures à vérifier
            
        Returns:
            bool: True si équilibré
            
        Raises:
            ValueError: Si déséquilibre détecté
        """
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for ecriture in ecritures:
            if ecriture.compte_debit:
                total_debit += Decimal(str(ecriture.montant))
            if ecriture.compte_credit:
                total_credit += Decimal(str(ecriture.montant))
        
        # Tolérance de 0.01 pour les arrondis
        if abs(total_debit - total_credit) > Decimal('0.01'):
            raise ValueError(
                f"Écriture comptable déséquilibrée. "
                f"Total Débit: {total_debit}, Total Crédit: {total_credit}, "
                f"Écart: {abs(total_debit - total_credit)}"
            )
        
        return True

    def _verifier_equilibre_simple(
        self,
        compte_debit: str,
        compte_credit: str,
        montant: Decimal
    ) -> bool:
        """
        Vérifie l'équilibre d'une écriture simple (1 débit = 1 crédit).
        """
        if not compte_debit or not compte_credit:
            raise ValueError("Les comptes débit et crédit sont obligatoires")

        if compte_debit == compte_credit:
            raise ValueError("Les comptes débit et crédit doivent être différents")

        if montant <= 0:
            raise ValueError("Le montant doit être strictement positif")

        return True

    def _appliquer_tracabilite_creation(
        self,
        ecriture: EcritureComptable,
        cree_par_id: Optional[int] = None,
        reference_id: Optional[int] = None,
    ) -> None:
        """Applique les champs de traçabilité à une écriture."""
        now = datetime.utcnow()
        ecriture.date_creation = now
        user_id = cree_par_id if cree_par_id is not None else self.cree_par_id
        if user_id is not None:
            ecriture.cree_par = user_id
        if reference_id is not None:
            ecriture.reference_id = reference_id
        elif ecriture.id_amortissement:
            ecriture.reference_id = ecriture.id_amortissement
        if ecriture.date_ecriture:
            ecriture.periode_comptable = ecriture.date_ecriture.strftime("%Y-%m")
        ecriture.journal = self._journal_pour_type(ecriture.type_operation)

    def _get_compte_immobilisation(self, type_bien: str) -> str:
        """Compte d'immobilisation corporelle (classe 2 SYSCOHADA)."""
        compte_map = {
            "vehicule": "2445",
            "machine": "2441",
            "ordinateur": "2443",
            "mobilier": "2448",
            "autre": "2440",
        }
        return compte_map.get(type_bien, "2440")

    def get_compte_amortissement_par_categorie(self, categorie: str) -> tuple:
        """Retourne le compte de dotation et le compte d'amortissement."""
        regle = self.db.query(RegleAmortissement).filter(
            RegleAmortissement.categorie_bien == categorie,
            RegleAmortissement.est_active == True
        ).first()

        if regle and regle.compte_dotation and regle.compte_amortissement:
            return (regle.compte_dotation, regle.compte_amortissement)

        compte_map = {
            "vehicule": ("6812", "2845"),
            "ordinateur": ("6812", "2843"),
            "machine": ("6812", "2841"),
            "mobilier": ("6812", "2848"),
            "autre": ("6812", "2840")
        }
        return compte_map.get(categorie, ("6812", "2840"))

    def _get_compte_amortissement_credit(self, type_bien: str) -> str:
        """Compte d'amortissement crédit pour cession."""
        compte_map = {
            "vehicule": "2845",
            "ordinateur": "2843",
            "machine": "2841",
            "mobilier": "2848",
        }
        return compte_map.get(type_bien, "2840")

    def _calculer_vnc(self, bien: Bien) -> float:
        """Calcule la Valeur Nette Comptable d'un bien."""
        brut = float(bien.prix_acquisition or 0)
        cumul_amo = float(bien.cumul_amortissement or 0)
        cumul_dep = float(bien.cumul_depreciation or 0)
        return self._round(max(0, brut - cumul_amo - cumul_dep))

    def _get_bien_designation(self, bien: Bien) -> str:
        """Récupère la désignation du bien."""
        if hasattr(bien, 'marque') and bien.marque:
            return f"{bien.marque} {getattr(bien, 'modele', '')}".strip()
        if hasattr(bien, 'fabricant') and bien.fabricant:
            return f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip()
        return f"Bien #{bien.id_bien}"

    # ============================================================
    # ÉCRITURE D'ACQUISITION
    # ============================================================

    def generer_ecriture_acquisition(self, bien: Bien) -> EcritureComptable:
        """
        Génère l'écriture d'acquisition d'un bien.
        Débit compte 24x / Crédit 481 (crédit) ou 512 (comptant).
        OHADA/SYSCOHADA
        """
        compte_debit = self._get_compte_immobilisation(bien.type_bien or "autre")

        if bien.mode_paiement == "comptant":
            compte_credit = "512"  # Banque
        else:
            compte_credit = "481"  # Fournisseur d'investissement

        montant = float(bien.prix_acquisition or 0)
        if montant <= 0:
            raise ValueError("Le prix d'acquisition doit être supérieur à 0")

        # ✅ Vérification de l'équilibre
        self._verifier_equilibre_simple(
            compte_debit=compte_debit,
            compte_credit=compte_credit,
            montant=Decimal(str(montant))
        )

        designation = self._get_bien_designation(bien)

        ecriture = EcritureComptable(
            id_bien=bien.id_bien,
            date_ecriture=datetime.utcnow(),
            exercice=datetime.utcnow().year,
            type_operation=TypeOperationEnum.ACQUISITION,
            statut=StatutEcriture.BROUILLON,
            libelle=f"Acquisition immobilisation - {designation}",
            compte_debit=compte_debit,
            compte_credit=compte_credit,
            montant=self._round(montant),
            montant_original=self._round(montant),
            validee=False,
        )

        self._appliquer_tracabilite_creation(ecriture, reference_id=bien.id_bien)
        self.db.add(ecriture)
        self.db.commit()
        self.db.refresh(ecriture)

        return ecriture

    # ============================================================
    # ÉCRITURES DE DOTATION
    # ============================================================

    def generer_ecriture_dotation(self, amortissement: Amortissement, type_bien: str) -> EcritureComptable:
        """Génère une écriture de dotation avec statut BROUILLON (non validée)."""
        compte_debit, compte_credit = self.get_compte_amortissement_par_categorie(type_bien)

        # ✅ Vérification de l'équilibre
        self._verifier_equilibre_simple(
            compte_debit=compte_debit,
            compte_credit=compte_credit,
            montant=Decimal(str(amortissement.annuite_comptable))
        )

        details_calcul = {
            "base": amortissement.valeur_origine - amortissement.valeur_residuelle,
            "taux": amortissement.taux_comptable,
            "methode": amortissement.methode.value,
            "prorata_jours": amortissement.jours_prorata if amortissement.methode.value == "LINEAIRE" else None,
            "prorata_mois": getattr(amortissement, 'mois_prorata', None),
            "coefficient": amortissement.coefficient_deg
        }

        ecriture = EcritureComptable(
            id_bien=amortissement.id_bien,
            id_amortissement=amortissement.id_amortissement,
            date_ecriture=datetime.utcnow(),
            exercice=amortissement.exercice,
            type_operation=TypeOperationEnum.DOTATION_AMORTISSEMENT,
            statut=StatutEcriture.BROUILLON,
            libelle=f"Dotation amortissement {amortissement.methode.value} - Exercice {amortissement.exercice}",
            compte_debit=compte_debit,
            compte_credit=compte_credit,
            montant=self._round(amortissement.annuite_comptable),
            montant_original=self._round(amortissement.annuite_comptable),
            details_calcul=str(details_calcul),
            validee=False
        )

        self._appliquer_tracabilite_creation(ecriture, reference_id=amortissement.id_amortissement)
        self.db.add(ecriture)
        self.db.commit()
        self.db.refresh(ecriture)

        return ecriture

    # ============================================================
    # ÉCRITURES DE DÉPRÉCIATION
    # ============================================================

    def generer_ecriture_depreciation(
        self,
        amortissement: Amortissement,
        montant_depreciation: float,
        date_depreciation: datetime
    ) -> EcritureComptable:
        """Génère une écriture de dépréciation."""
        # ✅ Vérification de l'équilibre
        self._verifier_equilibre_simple(
            compte_debit="6914",
            compte_credit="2944",
            montant=Decimal(str(montant_depreciation))
        )

        ecriture = EcritureComptable(
            id_bien=amortissement.id_bien,
            id_amortissement=amortissement.id_amortissement,
            date_ecriture=date_depreciation,
            exercice=date_depreciation.year,
            type_operation=TypeOperationEnum.DEPRECIATION,
            statut=StatutEcriture.BROUILLON,
            libelle=f"Dépréciation du bien - Nouvelle valeur: {amortissement.valeur_actualisee}",
            compte_debit="6914",
            compte_credit="2944",
            montant=self._round(montant_depreciation),
            montant_original=self._round(montant_depreciation),
            validee=False
        )

        self._appliquer_tracabilite_creation(ecriture, reference_id=amortissement.id_amortissement)
        self.db.add(ecriture)
        self.db.commit()
        self.db.refresh(ecriture)

        return ecriture

    # ============================================================
    # ÉCRITURES DE CESSION (AVEC VÉRIFICATION GLOBALE)
    # ============================================================

    def _generer_ecritures_cession(
        self,
        cession: Cession,
        bien: Bien,
        vnc: float,
        prix_vente: float,
        date_ecriture: datetime,
        motif: str = None,
    ) -> List[EcritureComptable]:
        """
        Génère les écritures de cession avec distinction courant/non courant.
        
        🔴 LE STATUT CEDE N'EST PAS MODIFIÉ ICI
        🔴 VÉRIFICATION GLOBALE DE L'ÉQUILIBRE AVANT PERSISTANCE
        """
        is_non_courante = cession.type_cession == "non_courante"

        if is_non_courante:
            compte_vnc = "81"
            compte_produit = "82"
            compte_plus_value = "775"
            compte_moins_value = "81"
        else:
            compte_vnc = "654"
            compte_produit = "754"
            compte_plus_value = "754"
            compte_moins_value = "654"

        compte_immobilisation = self._get_compte_immobilisation(bien.type_bien or "autre")
        compte_amort = self._get_compte_amortissement_credit(bien.type_bien or "autre")
        compte_encaissement = "512" if cession.mode_reglement == "comptant" else "411"

        designation = self._get_bien_designation(bien)
        libelle_base = motif or f"Cession {cession.type_cession} - {designation}"
        ecritures = []
        cumul_amo = float(bien.cumul_amortissement or 0)
        brut = float(bien.prix_acquisition or 0)

        # 1. Reprise des amortissements
        if cumul_amo > 0:
            ec_amo = EcritureComptable(
                id_bien=bien.id_bien,
                date_ecriture=date_ecriture,
                exercice=date_ecriture.year,
                type_operation=TypeOperationEnum.CESSION,
                statut=StatutEcriture.BROUILLON,
                libelle=f"{libelle_base} - Reprise amortissements",
                compte_debit=compte_amort,
                compte_credit=compte_immobilisation,
                montant=self._round(cumul_amo),
                montant_original=self._round(cumul_amo),
                validee=False,
            )
            self._appliquer_tracabilite_creation(ec_amo, reference_id=cession.id_cession)
            ecritures.append(ec_amo)

        # 2. Sortie de l'immobilisation
        vnc_courante = self._round(brut - cumul_amo)
        if vnc_courante > 0:
            ec_sortie = EcritureComptable(
                id_bien=bien.id_bien,
                date_ecriture=date_ecriture,
                exercice=date_ecriture.year,
                type_operation=TypeOperationEnum.CESSION,
                statut=StatutEcriture.BROUILLON,
                libelle=f"{libelle_base} - Sortie immobilisation",
                compte_debit=compte_vnc,
                compte_credit=compte_immobilisation,
                montant=vnc_courante,
                montant_original=vnc_courante,
                validee=False,
            )
            self._appliquer_tracabilite_creation(ec_sortie, reference_id=cession.id_cession)
            ecritures.append(ec_sortie)

        # 3. Produit de cession
        if prix_vente > 0:
            ec_vente = EcritureComptable(
                id_bien=bien.id_bien,
                date_ecriture=date_ecriture,
                exercice=date_ecriture.year,
                type_operation=TypeOperationEnum.CESSION,
                statut=StatutEcriture.BROUILLON,
                libelle=f"{libelle_base} - Produit de cession",
                compte_debit=compte_encaissement,
                compte_credit=compte_produit,
                montant=self._round(prix_vente),
                montant_original=self._round(prix_vente),
                validee=False,
            )
            self._appliquer_tracabilite_creation(ec_vente, reference_id=cession.id_cession)
            ecritures.append(ec_vente)

        # 4. Résultat de cession (plus-value ou moins-value)
        resultat = float(cession.resultat or 0)
        if resultat > 0:
            ec_res = EcritureComptable(
                id_bien=bien.id_bien,
                date_ecriture=date_ecriture,
                exercice=date_ecriture.year,
                type_operation=TypeOperationEnum.CESSION,
                statut=StatutEcriture.BROUILLON,
                libelle=f"{libelle_base} - Plus-value",
                compte_debit=compte_encaissement if prix_vente > 0 else "411",
                compte_credit=compte_plus_value,
                montant=self._round(resultat),
                montant_original=self._round(resultat),
                validee=False,
            )
            self._appliquer_tracabilite_creation(ec_res, reference_id=cession.id_cession)
            ecritures.append(ec_res)
        elif resultat < 0:
            ec_res = EcritureComptable(
                id_bien=bien.id_bien,
                date_ecriture=date_ecriture,
                exercice=date_ecriture.year,
                type_operation=TypeOperationEnum.CESSION,
                statut=StatutEcriture.BROUILLON,
                libelle=f"{libelle_base} - Moins-value",
                compte_debit=compte_moins_value,
                compte_credit="411",
                montant=self._round(abs(resultat)),
                montant_original=self._round(abs(resultat)),
                validee=False,
            )
            self._appliquer_tracabilite_creation(ec_res, reference_id=cession.id_cession)
            ecritures.append(ec_res)

        # 🔴 VÉRIFICATION GLOBALE DE L'ÉQUILIBRE AVANT PERSISTANCE
        self._verifier_equilibre(ecritures)

        return ecritures

    # ============================================================
    # MÉTHODE ENREGISTRER_CESSION – DÉPRÉCIÉE
    # ============================================================

    def enregistrer_cession(self, data: CessionCreate) -> tuple:
        """
        🔴 MÉTHODE DÉPRÉCIÉE

        Cette méthode changeait incorrectement le statut du bien à CEDE
        lors de la création de la cession.

        Le statut CEDE est désormais géré UNIQUEMENT par ValidationService
        lors de la validation de l'encaissement par le caissier.

        Utiliser ValidationService.valider_cession() à l'étape CAISSE.
        """
        logger.error(
            "ComptabiliteService.enregistrer_cession est DÉPRÉCIÉE et ne doit "
            "plus être utilisée. Le statut CEDE est géré par ValidationService."
        )
        raise RuntimeError(
            "Méthode dépréciée. Le statut CEDE est géré par ValidationService."
        )

    # ============================================================
    # MÉTHODES DE GESTION DES ÉCRITURES
    # ============================================================

    def modifier_montant_ecriture(
        self,
        id_ecriture: int,
        nouveau_montant: float,
        motif: str,
        id_modificateur: int
    ) -> Optional[EcritureComptable]:
        """Modifie le montant d'une écriture (si non validée)."""
        ecriture = self.db.query(EcritureComptable).filter(
            EcritureComptable.id_ecriture == id_ecriture
        ).first()

        if not ecriture or ecriture.validee:
            return None

        # ✅ Vérification que le nouveau montant est positif
        if nouveau_montant <= 0:
            raise ValueError("Le nouveau montant doit être strictement positif")

        ecriture.montant_original = ecriture.montant
        ecriture.montant = self._round(nouveau_montant)
        ecriture.motif_modification = motif
        ecriture.id_modificateur = id_modificateur
        ecriture.date_modification = datetime.utcnow()

        self.db.commit()
        self.db.refresh(ecriture)

        return ecriture

    def valider_ecriture(self, id_ecriture: int, id_validateur: int) -> Optional[EcritureComptable]:
        """Valide une écriture comptable."""
        ecriture = self.db.query(EcritureComptable).filter(
            EcritureComptable.id_ecriture == id_ecriture
        ).first()

        if not ecriture or ecriture.validee:
            return None

        ecriture.validee = True
        ecriture.statut = StatutEcriture.VALIDEE
        ecriture.date_validation = datetime.utcnow()
        ecriture.valide_par = id_validateur
        ecriture.id_validateur = id_validateur

        if ecriture.id_amortissement:
            amort = self.db.query(Amortissement).filter(
                Amortissement.id_amortissement == ecriture.id_amortissement
            ).first()
            if amort:
                amort.statut = StatutAmortissement.EN_COURS

        self.db.commit()
        self.db.refresh(ecriture)

        return ecriture

    def get_ecritures_en_attente(self) -> List[EcritureComptable]:
        """Récupère les écritures en attente de validation."""
        return self.db.query(EcritureComptable).filter(
            EcritureComptable.validee == False,
            EcritureComptable.statut == StatutEcriture.BROUILLON
        ).order_by(EcritureComptable.date_ecriture.asc()).all()

    def get_ecritures_du_jour(self, date_jour: datetime = None) -> List[EcritureComptable]:
        """Récupère les écritures validées du jour."""
        if not date_jour:
            date_jour = datetime.utcnow()

        debut_jour = datetime(date_jour.year, date_jour.month, date_jour.day)
        fin_jour = datetime(date_jour.year, date_jour.month, date_jour.day, 23, 59, 59)

        return self.db.query(EcritureComptable).filter(
            EcritureComptable.date_ecriture.between(debut_jour, fin_jour),
            EcritureComptable.validee == True
        ).order_by(EcritureComptable.date_ecriture.asc()).all()