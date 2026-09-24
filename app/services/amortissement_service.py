# backend/app/services/amortissement_service.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from ..models.ecriture_comptable import StatutEcriture
from ..schemas.cloture import BienPrevisualisation
from ..models.amortissement import Amortissement, MethodeAmortissement, StatutAmortissement
from ..models.regles_amortissement import RegleAmortissement
from ..models.bien import Bien
from ..models.composant import Composant
from ..models.alerte_vnc import AlerteVNC, StatutAlerteVNC
from ..models.journal_evenements_immobilisation import JournalEvenementImmobilisation, TypeEvenementImmobilisation
from ..schemas.amortissement import AmortissementCreate, PlanAmortissementRow
from ..schemas.amortissement import MethodeEnum 
from .notification_trigger_service import NotificationTriggerService
from sqlalchemy import func, or_

from ..core.constants import (
    SEUIL_VNC_CRITIQUE,
    SEUIL_VNC_STANDARD,
    FACTEUR_FREQUENCE_PANNES,
    POIDS_COUT_REPARATION
)

import logging

logger = logging.getLogger(__name__)


class AmortissementService:
    def __init__(self, db: Session):
        self.db = db
        self.JOURS_ANNEE = 360
        self.JOURS_MOIS = 30

    def _to_decimal(self, value: float, precision: int = 2) -> Decimal:
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def _ensure_naive(self, dt: Any) -> datetime:
        if dt is None:
            return datetime.now()
        if isinstance(dt, date) and not isinstance(dt, datetime):
            return datetime(dt.year, dt.month, dt.day)
        if hasattr(dt, 'tzinfo') and getattr(dt, 'tzinfo', None) is not None:
            return dt.replace(tzinfo=None)
        return dt

    # ═══ 5.22 — Helpers multi-tenant ═══
    def _get_organisation_id_bien(self, id_bien: Optional[int]) -> Optional[int]:
        """Récupère l'organisation_id d'un Bien (None si introuvable)."""
        if not id_bien:
            return None
        bien = self.db.query(Bien).filter(Bien.id_bien == id_bien).first()
        return getattr(bien, "organisation_id", None) if bien else None

    def _check_acces_bien_id(self, id_bien: int, organisation_id: Optional[int]) -> None:
        """Vérifie que le bien appartient à l'organisation (None = admin plateforme)."""
        if organisation_id is None:
            return
        bien_org = self._get_organisation_id_bien(id_bien)
        if bien_org is None:
            raise ValueError(
                f"Accès refusé : bien #{id_bien} sans organisation (donnée historique)."
            )
        if bien_org != organisation_id:
            raise ValueError(
                f"Accès refusé : bien #{id_bien} appartient à une autre organisation."
            )

    def _check_acces_amortissement(self, amortissement: Amortissement, organisation_id: Optional[int]) -> None:
        """Vérifie que l'amortissement appartient à l'organisation (None = admin plateforme)."""
        if organisation_id is None or not amortissement:
            return
        org = getattr(amortissement, "organisation_id", None)
        if org is None:
            # Fallback : vérifier via le bien
            self._check_acces_bien_id(amortissement.id_bien, organisation_id)
            return
        if org != organisation_id:
            raise ValueError(
                f"Accès refusé : amortissement #{amortissement.id_amortissement} appartient à une autre organisation."
            )
    # ═══ FIN 5.22 ═══

    def _calculer_jours_prorata_lineaire(self, date_mise_en_service: datetime, exercice: int) -> int:
        date_mise_en_service = self._ensure_naive(date_mise_en_service)
        debut_annee = datetime(exercice, 1, 1)
        if date_mise_en_service <= debut_annee:
            return self.JOURS_ANNEE
        mois_restants = (12 - date_mise_en_service.month) + 1
        jours_restants_mois = (self.JOURS_MOIS - date_mise_en_service.day + 1) if date_mise_en_service.day <= self.JOURS_MOIS else 0
        jours = jours_restants_mois + (mois_restants - 1) * self.JOURS_MOIS
        return min(jours, self.JOURS_ANNEE)

    def _calculer_mois_prorata_degressif(self, date_acquisition: datetime, exercice: int) -> int:
        date_acquisition = self._ensure_naive(date_acquisition)
        debut_mois_acquisition = date(date_acquisition.year, date_acquisition.month, 1)
        if debut_mois_acquisition.year < exercice:
            return 12
        elif debut_mois_acquisition.year > exercice:
            return 0
        else:
            return 12 - debut_mois_acquisition.month + 1

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_regle_par_categorie(self, categorie: str, organisation_id: Optional[int] = None) -> Optional[RegleAmortissement]:
        """Retourne la règle active pour cette catégorie.
        Si organisation_id fourni → filtre sur cette ONG.
        Sinon → fallback legacy (toutes ONG)."""
        query = self.db.query(RegleAmortissement).filter(
            RegleAmortissement.categorie_bien == categorie,
            RegleAmortissement.est_active == True
        )
        if organisation_id is not None:
            query = query.filter(RegleAmortissement.organisation_id == organisation_id)
        regle = query.first()

        if not regle:
            regle = RegleAmortissement(
                categorie_bien=categorie,
                duree_vie_ans=5,
                taux_fiscal=20.0,
                coeff_deg_3_4_ans=1.5,
                coeff_deg_5_6_ans=2.0,
                coeff_deg_7_plus_ans=2.5,
                compte_dotation="6812",
                base_jours_annee=360,
                prorata_debut_mois=True,
                organisation_id=organisation_id,   # ═══ 5.22 ═══
            )
        return regle
    # ═══ FIN MODIF 5.22 ═══

    def get_coefficient_degressif(self, duree_ans: int, regle: RegleAmortissement) -> float:
        if duree_ans <= 4:
            return regle.coeff_deg_3_4_ans
        elif duree_ans <= 6:
            return regle.coeff_deg_5_6_ans
        else:
            return regle.coeff_deg_7_plus_ans

    def calculer_annuite_lineaire_rdc(self, base_amortissable: float, taux: float, date_mise_en_service: datetime, exercice: int) -> float:
        base_dec = self._to_decimal(base_amortissable)
        taux_dec = self._to_decimal(taux / 100)
        jours = self._calculer_jours_prorata_lineaire(date_mise_en_service, exercice)
        annuite = base_dec * taux_dec * Decimal(jours) / Decimal(self.JOURS_ANNEE)
        return float(annuite)

    def calculer_annuite_degressive_rdc(self, vnc: float, duree_totale_initiale: int, coefficient: float, 
                                         date_acquisition: datetime, exercice: int, annee_numero: int) -> float:
        vnc_dec = self._to_decimal(vnc)
        taux_lineaire_base = Decimal(100 / duree_totale_initiale) / Decimal(100)
        taux_degressif = taux_lineaire_base * Decimal(coefficient)
        if annee_numero == 1:
            mois = self._calculer_mois_prorata_degressif(date_acquisition, exercice)
            annuite = vnc_dec * taux_degressif * Decimal(mois) / Decimal(12)
        else:
            annuite = vnc_dec * taux_degressif
            lineaire_residuel = vnc_dec / Decimal(duree_totale_initiale - annee_numero + 1)
            annuite = max(annuite, lineaire_residuel)
        return float(annuite)

    def calculer_annuite_uop(self, base_amortissable: float, unites_conso: int, unites_total: int) -> float:
        if unites_total == 0:
            return 0.0
        base_dec = self._to_decimal(base_amortissable)
        annuite = base_dec * Decimal(unites_conso) / Decimal(unites_total)
        return float(annuite)

    def calculer_annuite_okapi(self, base: float, duree_fournisseur: int, jours_ouvres: int, jours_utilises: int) -> float:
        if duree_fournisseur == 0:
            return 0.0
        base_dec = self._to_decimal(base)
        taux_df = base_dec / Decimal(duree_fournisseur)
        journalier = taux_df / Decimal(jours_ouvres)
        annuite = journalier * Decimal(jours_utilises)
        return float(annuite)

    def calculer_amortissement_composants(
        self,
        id_bien: int,
        exercice: int,
        base_fiscale: float = None,
        duree_structure_ans: Optional[int] = None,
        date_mise_en_service_bien: Optional[datetime] = None,
    ) -> Dict:
        composants = self.db.query(Composant).filter(Composant.id_bien == id_bien).all()
        if not composants:
            raise ValueError(
                "Aucun composant défini pour ce bien. Décomposez le bien en composants "
                "(fiche bien → Décomposition OHADA) avant d'utiliser la méthode par composants."
            )

        bien = self.db.query(Bien).filter(Bien.id_bien == id_bien).first()
        if not bien:
            raise ValueError("Bien non trouvé")

        if date_mise_en_service_bien:
            date_defaut_bien = self._to_datetime(date_mise_en_service_bien)
        elif bien.date_acquisition:
            date_defaut_bien = self._to_datetime(bien.date_acquisition)
        else:
            date_defaut_bien = datetime.utcnow()

        annuite_totale = 0.0
        details = []
        for comp in composants:
            if not comp.duree_vie_ans or comp.duree_vie_ans <= 0:
                raise ValueError(f"Durée de vie invalide pour le composant {comp.designation}")

            base_comp = float(comp.valeur or 0)
            if base_comp <= 0:
                raise ValueError(f"Valeur invalide pour le composant {comp.designation}")

            date_ref = (
                self._to_datetime(comp.date_mise_en_service)
                if comp.date_mise_en_service
                else date_defaut_bien
            )
            taux_comp = 100.0 / comp.duree_vie_ans
            annuite_comp = self.calculer_annuite_lineaire_rdc(
                base_comp,
                taux_comp,
                date_ref,
                exercice,
            )
            annuite_totale += annuite_comp
            details.append({
                "id": comp.id_composant,
                "designation": comp.designation,
                "valeur": comp.valeur,
                "duree_vie": comp.duree_vie_ans,
                "annuite": round(annuite_comp, 2),
            })

        somme_composants = sum(float(c.valeur or 0) for c in composants)
        valeur_structure = float(bien.prix_acquisition or 0) - somme_composants
        if valeur_structure > 0.01:
            regle = self.get_regle_par_categorie(
                bien.type_bien or "autre",
                organisation_id=getattr(bien, "organisation_id", None),   # ═══ 5.22 ═══
            )
            duree_structure = duree_structure_ans or (regle.duree_vie_ans if regle else 5)
            if duree_structure <= 0:
                raise ValueError("Durée de vie invalide pour la structure résiduelle")
            taux_structure = 100.0 / duree_structure
            annuite_structure = self.calculer_annuite_lineaire_rdc(
                valeur_structure,
                taux_structure,
                date_defaut_bien,
                exercice,
            )
            annuite_totale += annuite_structure
            details.append({
                "id": None,
                "designation": "Structure résiduelle",
                "valeur": round(valeur_structure, 2),
                "duree_vie": duree_structure,
                "annuite": round(annuite_structure, 2),
            })

        base_fiscale_val = base_fiscale if base_fiscale is not None else self.get_base_fiscale(id_bien)
        taux_fiscal = self.get_taux_fiscal_from_regle(
            self.get_categorie_bien(id_bien),
            organisation_id=getattr(bien, "organisation_id", None),   # ═══ 5.22 ═══
        )
        annuite_fiscale = self.calculer_annuite_lineaire_rdc(
            base_fiscale_val,
            taux_fiscal,
            date_defaut_bien,
            exercice,
        )

        return {
            "composants": details,
            "annuite_totale_comptable": round(annuite_totale, 2),
            "annuite_fiscale_globale": round(annuite_fiscale, 2),
        }

    def get_categorie_bien(self, id_bien: int) -> str:
        bien = self.db.query(Bien).filter(Bien.id_bien == id_bien).first()
        if bien:
            return bien.type_bien or "autre"
        return "autre"

    def get_base_fiscale(self, id_bien: int) -> float:
        bien = self.db.query(Bien).filter(Bien.id_bien == id_bien).first()
        if bien:
            return float(bien.prix_acquisition) if bien.prix_acquisition else 0.0
        return 0.0

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_taux_fiscal_from_regle(self, categorie: str, organisation_id: Optional[int] = None) -> float:
        regle = self.get_regle_par_categorie(categorie, organisation_id=organisation_id)
        return regle.taux_fiscal if regle else 20.0
    # ═══ FIN MODIF 5.22 ═══

    def calculer_ecart(self, comptable: float, fiscal: float) -> float:
        return round(comptable - fiscal, 2)

    def appliquer_depreciation(self, amortissement: Amortissement, nouvelle_valeur: float, date_depreciation: datetime) -> Amortissement:
        ancienne_vnc = amortissement.valeur_nette_comptable
        montant_depreciation = ancienne_vnc - nouvelle_valeur
        if montant_depreciation <= 0:
            return amortissement
        amortissement.valeur_actualisee = nouvelle_valeur
        amortissement.date_depreciation = date_depreciation
        amortissement.montant_depreciation = montant_depreciation
        amortissement.valeur_nette_comptable = nouvelle_valeur
        self.db.commit()
        self.db.refresh(amortissement)
        return amortissement

    def calculer_plan_complet(self, amort: Amortissement) -> List[PlanAmortissementRow]:
        plan = []
        vnc_c = amort.valeur_origine
        vnc_f = amort.valeur_origine
        cumul_c = 0.0
        cumul_f = 0.0
        base = amort.valeur_origine - amort.valeur_residuelle
        if amort.valeur_actualisee and amort.date_depreciation:
            vnc_c = amort.valeur_actualisee
            base = amort.valeur_actualisee - amort.valeur_residuelle
        regle = self.get_regle_par_categorie(
            self.get_categorie_bien(amort.id_bien),
            organisation_id=getattr(amort, "organisation_id", None),   # ═══ 5.22 ═══
        )
        duree_totale_initiale = amort.duree_vie_comptable_ans
        for i in range(1, amort.duree_vie_comptable_ans + 1):
            annuite_c = 0.0
            if amort.methode == MethodeEnum.LINEAIRE:
                annuite_c = self.calculer_annuite_lineaire_rdc(
                    base, amort.taux_comptable, amort.date_mise_en_service, amort.exercice + i - 1
                )
                if i > 1:
                    annuite_c = self.calculer_annuite_lineaire_rdc(
                        base, amort.taux_comptable, datetime(amort.exercice + i - 1, 1, 1), amort.exercice + i - 1
                    )
            elif amort.methode == MethodeEnum.DEGRESSIF:
                coeff = self.get_coefficient_degressif(duree_totale_initiale, regle)
                annuite_c = self.calculer_annuite_degressive_rdc(
                    vnc_c, duree_totale_initiale, coeff, amort.date_acquisition, amort.exercice, i
                )
            elif amort.methode == MethodeEnum.UNITE_PRODUCTION:
                total_prevue = amort.production_totale_prevue or 1
                conso = amort.production_reelle_exercice if i == 1 else 0
                annuite_c = self.calculer_annuite_uop(base, conso, total_prevue)
            elif amort.methode == MethodeEnum.SPECIFIQUE_OKAPI:
                annuite_c = self.calculer_annuite_okapi(
                    base, amort.duree_fournisseur or 1, 
                    amort.jours_ouvres_mois or 26, amort.jours_utilisation_annee or 260
                )
            elif amort.methode == MethodeEnum.COMPOSANTS:
                result = self.calculer_amortissement_composants(
                    amort.id_bien,
                    amort.exercice + i - 1,
                    base,
                    duree_structure_ans=int(amort.duree_vie_comptable_ans),
                    date_mise_en_service_bien=amort.date_mise_en_service,
                )
                annuite_c = result["annuite_totale_comptable"]
            annuite_c = min(annuite_c, vnc_c)
            annuite_f = self.calculer_annuite_lineaire_rdc(
                base, amort.taux_fiscal, amort.date_mise_en_service, amort.exercice + i - 1
            )
            annuite_f = min(annuite_f, vnc_f)
            plan.append(self._create_plan_row(
                amort.exercice + i - 1, amort, vnc_c, vnc_f, annuite_c, annuite_f, cumul_c, cumul_f
            ))
            vnc_c -= annuite_c
            vnc_f -= annuite_f
            cumul_c += annuite_c
            cumul_f += annuite_f
        return plan

    def _create_plan_row(self, annee: int, amort: Amortissement, vnc_c: float, vnc_f: float, 
                          annuite_c: float, annuite_f: float, cumul_c: float, cumul_f: float) -> PlanAmortissementRow:
        ecart = self.calculer_ecart(annuite_c, annuite_f)
        return PlanAmortissementRow(
            annee=annee,
            vnc_debut_c=round(vnc_c, 2),
            vnc_debut_f=round(vnc_f, 2),
            annuite_c=round(annuite_c, 2),
            annuite_f=round(annuite_f, 2),
            ecart=round(ecart, 2),
            cumul_c=round(cumul_c + annuite_c, 2),
            cumul_f=round(cumul_f + annuite_f, 2),
            vnc_fin_c=round(vnc_c - annuite_c, 2),
            vnc_fin_f=round(vnc_f - annuite_f, 2)
        )

    # ============================================================
    # CRÉATION D'AMORTISSEMENT (AVEC INJECTION organisation_id)
    # ============================================================

    def creer_amortissement(self, data: AmortissementCreate, type_bien: str) -> Amortissement:
        """
        Crée un amortissement et met à jour le statut comptable du bien.
        🔴 TÂCHE 2 : valeur_residuelle FORCÉE À 0
        🔴 5.22 : injection automatique de organisation_id depuis le Bien
        """
        try:
            bien = self.db.query(Bien).filter(
                Bien.id_bien == data.id_bien
            ).first()

            if not bien:
                raise ValueError("Bien non trouvé")

            if bien.statut_comptable in ["CEDE", "MIS_AU_REBUT"]:
                raise ValueError(f"Impossible d'amortir un bien {bien.statut_comptable}")

            # ═══ 5.22 — organisation_id depuis le Bien ═══
            org_id = getattr(bien, "organisation_id", None)
            # ═══ FIN 5.22 ═══

            base_amortissable = data.valeur_origine

            regle = self.get_regle_par_categorie(type_bien, organisation_id=org_id)   # ═══ 5.22 ═══
            duree_comptable = data.duree_vie_comptable_ans
            if duree_comptable <= 0:
                raise ValueError("La durée de vie comptable doit être supérieure à 0.")

            duree_fiscale = data.duree_vie_fiscale_ans or (regle.duree_vie_ans if regle else duree_comptable)
            taux_fiscal = regle.taux_fiscal if regle else (100.0 / duree_fiscale)
            annuite_comptable = 0.0
            from datetime import datetime as dt_class
            date_acq = data.date_acquisition or bien.date_acquisition or dt_class(data.exercice, 1, 1)
            date_mes = data.date_mise_en_service or date_acq

            if data.methode == MethodeEnum.LINEAIRE:
                duree_comptable = float(data.duree_vie_comptable_ans)
                taux_comptable = 100.0 / duree_comptable
                annuite_comptable = self.calculer_annuite_lineaire_rdc(
                    base_amortissable, taux_comptable, date_mes, data.exercice
                )
            elif data.methode == MethodeEnum.DEGRESSIF:
                duree_comptable = float(data.duree_vie_comptable_ans)
                coeff = data.coefficient_deg or self.get_coefficient_degressif(duree_comptable, regle)
                taux_lineaire_base = 100.0 / duree_comptable
                taux_comptable = taux_lineaire_base * coeff
                annuite_comptable = self.calculer_annuite_degressive_rdc(
                    base_amortissable, duree_comptable, coeff, date_acq, data.exercice, 1
                )
            elif data.methode == MethodeEnum.UNITE_PRODUCTION:
                if not data.unites_totales_prevues or data.unites_totales_prevues <= 0:
                    raise ValueError("Les unités totales prévues doivent être supérieures à 0 pour cette méthode.")
                annuite_comptable = self.calculer_annuite_uop(
                    base_amortissable, data.unites_consommees_exercice or 0, data.unites_totales_prevues
                )
                taux_comptable = (annuite_comptable / base_amortissable) * 100 if base_amortissable > 0 else 0
            elif data.methode == MethodeEnum.SPECIFIQUE_OKAPI:
                if not data.duree_fournisseur or data.duree_fournisseur <= 0:
                    raise ValueError("La durée fournisseur (DF) est requise et doit être > 0.")
                annuite_comptable = self.calculer_annuite_okapi(
                    base_amortissable, data.duree_fournisseur, data.jours_ouvres_mois or 26, data.jours_utilisation_annee or 260
                )
                taux_comptable = (annuite_comptable / base_amortissable) * 100 if base_amortissable > 0 else 0
            elif data.methode == MethodeEnum.COMPOSANTS:
                result = self.calculer_amortissement_composants(
                    data.id_bien,
                    data.exercice,
                    base_amortissable,
                    duree_structure_ans=int(data.duree_vie_comptable_ans),
                    date_mise_en_service_bien=data.date_mise_en_service,
                )
                annuite_comptable = result["annuite_totale_comptable"]
                taux_comptable = (annuite_comptable / base_amortissable) * 100 if base_amortissable > 0 else 0

            annuite_fiscale = self.calculer_annuite_lineaire_rdc(
                base_amortissable, taux_fiscal, date_mes, data.exercice
            )
            ecart = self.calculer_ecart(annuite_comptable, annuite_fiscale)

            amortissement = Amortissement(
                id_bien=data.id_bien,
                exercice=data.exercice,
                methode=data.methode,
                valeur_origine=data.valeur_origine,
                valeur_residuelle=0.0,
                duree_vie_comptable_ans=duree_comptable,
                duree_vie_fiscale_ans=duree_fiscale,
                taux_comptable=round(taux_comptable, 2),
                taux_fiscal=round(taux_fiscal, 2),
                coefficient_deg=data.coefficient_deg,
                jours_prorata=self.JOURS_ANNEE,
                date_acquisition=date_acq,
                date_mise_en_service=date_mes,
                unites_totales_prevues=data.unites_totales_prevues,
                unites_consommees_exercice=data.unites_consommees_exercice,
                production_totale_prevue=data.production_totale_prevue,
                production_reelle_exercice=data.production_reelle_exercice,
                duree_fournisseur=data.duree_fournisseur,
                jours_ouvres_mois=data.jours_ouvres_mois,
                jours_utilisation_annee=data.jours_utilisation_annee,
                annuite_comptable=round(annuite_comptable, 2),
                annuite_fiscale=round(annuite_fiscale, 2),
                ecart_a_reintegrer=round(ecart, 2),
                cumul_comptable=round(annuite_comptable, 2),
                cumul_fiscal=round(annuite_fiscale, 2),
                valeur_nette_comptable=round(data.valeur_origine - annuite_comptable, 2),
                valeur_nette_fiscale=round(data.valeur_origine - annuite_fiscale, 2),
                date_debut=date_mes,
                statut=StatutAmortissement.EN_COURS,
                organisation_id=org_id,   # ═══ 5.22 — AJOUT ═══
            )

            self.db.add(amortissement)

            existing_amorts = self.db.query(Amortissement).filter(
                Amortissement.id_bien == data.id_bien
            ).count()

            if existing_amorts == 0:
                bien.statut_comptable = "EN_AMORTISSEMENT"

            cumul_actuel = float(bien.cumul_amortissement or 0)
            bien.cumul_amortissement = round(cumul_actuel + amortissement.annuite_comptable, 2)
            self.db.flush()

        except SQLAlchemyError as e:
            logger.error(f"Erreur création amortissement: {e}")
            raise ValueError(f"Échec de la création: {str(e)}")

        self.db.refresh(amortissement)

        try:
            trigger_service = NotificationTriggerService(self.db)
            trigger_service.notifier_amortissement_calcule(amortissement)
        except Exception as e:
            logger.warning(f"Erreur notification (non bloquante): {e}")

        return amortissement

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def get_historique_par_bien(self, id_bien: int, organisation_id: Optional[int] = None) -> List[Amortissement]:
        self._check_acces_bien_id(id_bien, organisation_id)
        return self.db.query(Amortissement).filter(
            Amortissement.id_bien == id_bien
        ).order_by(Amortissement.exercice.desc()).all()

    def get_plan_amortissement(self, id_bien: int, organisation_id: Optional[int] = None) -> List[PlanAmortissementRow]:
        self._check_acces_bien_id(id_bien, organisation_id)
        amort = self.db.query(Amortissement).filter(
            Amortissement.id_bien == id_bien
        ).order_by(Amortissement.exercice.desc()).first()
        if not amort:
            return []
        return self.calculer_plan_complet(amort)

    def get_statistiques(self, annee: int = None, organisation_id: Optional[int] = None) -> Dict:
        query = self.db.query(Amortissement)
        if organisation_id is not None:
            query = query.filter(Amortissement.organisation_id == organisation_id)
        if annee:
            query = query.filter(Amortissement.exercice == annee)

        total_amortissements_comptables = query.with_entities(func.sum(Amortissement.annuite_comptable)).scalar() or 0
        total_amortissements_fiscaux = query.with_entities(func.sum(Amortissement.annuite_fiscale)).scalar() or 0
        total_ecarts = query.with_entities(func.sum(Amortissement.ecart_a_reintegrer)).scalar() or 0
        economie_impot = total_amortissements_fiscaux * 0.30

        alertes_query = self.db.query(Amortissement).filter(
            Amortissement.valeur_nette_comptable <= Amortissement.valeur_origine * 0.10,
            Amortissement.statut == StatutAmortissement.EN_COURS
        )
        if organisation_id is not None:
            alertes_query = alertes_query.filter(Amortissement.organisation_id == organisation_id)
        alertes_fin_vie = alertes_query.count()

        return {
            "total_amortissements_comptables": round(total_amortissements_comptables, 2),
            "total_amortissements_fiscaux": round(total_amortissements_fiscaux, 2),
            "total_ecarts_a_reintegrer": round(total_ecarts, 2),
            "economie_impot_annuelle": round(economie_impot, 2),
            "details_par_categorie": {},
            "details_par_methode": {},
            "alertes_fin_vie": alertes_fin_vie
        }

    def get_ecarts_fiscaux(self, annee: int, organisation_id: Optional[int] = None) -> List[Dict]:
        query = self.db.query(Amortissement).filter(Amortissement.exercice == annee)
        if organisation_id is not None:
            query = query.filter(Amortissement.organisation_id == organisation_id)
        amortissements = query.all()
        return [
            {
                "id_bien": a.id_bien,
                "designation": a.bien.marque if hasattr(a.bien, 'marque') else f"Bien {a.id_bien}",
                "annuite_comptable": round(a.annuite_comptable, 2),
                "annuite_fiscale": round(a.annuite_fiscale, 2),
                "ecart_a_reintegrer": round(a.ecart_a_reintegrer, 2)
            }
            for a in amortissements
        ]

    def get_regles_configuration(self, organisation_id: Optional[int] = None) -> List[Dict]:
        query = self.db.query(RegleAmortissement)
        if organisation_id is not None:
            query = query.filter(RegleAmortissement.organisation_id == organisation_id)
        regles = query.all()
        return [
            {
                "id_regle": r.id_regle,
                "categorie_bien": r.categorie_bien,
                "duree_vie_ans": r.duree_vie_ans,
                "taux_fiscal": r.taux_fiscal,
                "coeff_deg_3_4_ans": r.coeff_deg_3_4_ans,
                "coeff_deg_5_6_ans": r.coeff_deg_5_6_ans,
                "coeff_deg_7_plus_ans": r.coeff_deg_7_plus_ans,
                "compte_dotation": r.compte_dotation,
                "base_jours_annee": r.base_jours_annee,
                "est_active": r.est_active
            }
            for r in regles
        ]

    def update_regle_configuration(self, id_regle: int, data: Dict, utilisateur: str, organisation_id: Optional[int] = None) -> Optional[RegleAmortissement]:
        query = self.db.query(RegleAmortissement).filter(RegleAmortissement.id_regle == id_regle)
        if organisation_id is not None:
            query = query.filter(RegleAmortissement.organisation_id == organisation_id)
        regle = query.first()
        if not regle:
            return None
        for key, value in data.items():
            if hasattr(regle, key):
                setattr(regle, key, value)
        regle.date_modification = datetime.utcnow()
        regle.modifie_par = utilisateur
        self.db.commit()
        self.db.refresh(regle)
        return regle
    # ═══ FIN MODIF 5.22 ═══

    # ═══ MODIF 5.22 — Vérif accès + inject organisation_id ═══
    def appliquer_depreciation(self, id_bien: int, nouvelle_valeur: float, motif: str, date_depreciation: datetime, organisation_id: Optional[int] = None) -> Amortissement:
        """Applique une dépréciation et met à jour le statut comptable."""
        self._check_acces_bien_id(id_bien, organisation_id)
        try:
            with self.db.begin():
                amortissement = self.db.query(Amortissement).filter(
                    Amortissement.id_bien == id_bien,
                    Amortissement.statut == StatutAmortissement.EN_COURS
                ).with_for_update().first()

                if not amortissement:
                    raise ValueError("Aucun amortissement en cours trouvé pour ce bien")

                bien = self.db.query(Bien).filter(Bien.id_bien == id_bien).with_for_update().first()
                if not bien:
                    raise ValueError("Bien non trouvé")

                if bien.statut_comptable in ["CEDE", "MIS_AU_REBUT"]:
                    raise ValueError(f"Impossible de déprécier un bien {bien.statut_comptable}")

                if bien.statut_comptable == "EN_DEPRECIATION":
                    raise ValueError("Ce bien est déjà en dépréciation")

                ancienne_vnc = amortissement.valeur_nette_comptable
                montant_depreciation = ancienne_vnc - nouvelle_valeur
                if montant_depreciation <= 0:
                    raise ValueError("La nouvelle valeur doit être inférieure à la VNC actuelle")

                amortissement.valeur_actualisee = nouvelle_valeur
                amortissement.date_depreciation = date_depreciation
                amortissement.montant_depreciation = montant_depreciation
                amortissement.valeur_nette_comptable = nouvelle_valeur

                # ═══ 5.22 — Injection organisation_id si absent ═══
                if getattr(amortissement, "organisation_id", None) is None:
                    amortissement.organisation_id = getattr(bien, "organisation_id", None)
                # ═══ FIN 5.22 ═══

                bien.statut_comptable = "EN_DEPRECIATION"
                cumul_actuel = float(bien.cumul_depreciation or 0)
                bien.cumul_depreciation = round(cumul_actuel + montant_depreciation, 2)

        except SQLAlchemyError as e:
            logger.error(f"Erreur application dépréciation: {e}")
            raise ValueError(f"Échec de la dépréciation: {str(e)}")

        self.db.refresh(amortissement)
        return amortissement
    # ═══ FIN MODIF 5.22 ═══

    def _to_datetime(self, value) -> datetime:
        if isinstance(value, datetime):
            return self._ensure_naive(value)
        if hasattr(value, "year") and not isinstance(value, datetime):
            return datetime(value.year, value.month, value.day)
        return datetime.utcnow()

    def _construire_donnees_amortissement(self, bien: Bien, exercice: int, methode_forcee: Optional[str] = None) -> AmortissementCreate:
        regle = self.get_regle_par_categorie(
            bien.type_bien or "autre",
            organisation_id=getattr(bien, "organisation_id", None),   # ═══ 5.22 ═══
        )
        date_ref = self._to_datetime(bien.date_acquisition)
        prix = float(bien.prix_acquisition or 0)

        if methode_forcee:
            try:
                methode = MethodeEnum(methode_forcee.upper())
            except ValueError:
                methode = MethodeEnum.LINEAIRE
        else:
            methode = MethodeEnum.LINEAIRE

        return AmortissementCreate(
            id_bien=bien.id_bien,
            exercice=exercice,
            methode=methode,
            valeur_origine=prix,
            valeur_residuelle=0.0,
            duree_vie_comptable_ans=regle.duree_vie_ans,
            duree_vie_fiscale_ans=regle.duree_vie_ans,
            date_acquisition=date_ref,
            date_mise_en_service=date_ref,
        )

    # ═══ MODIF 5.22 — Filtre organisation_id ═══
    def generer_amortissements_massifs(self, exercice: int, organisation_id: Optional[int] = None) -> dict:
        """
        Génère les amortissements pour tous les biens actifs.
        Cette méthode est appelée par le CRON ou via BackgroundTasks.
        """
        existing_ids = self.db.query(Amortissement.id_bien).filter(
            Amortissement.exercice == exercice
        )

        biens_query = self.db.query(Bien).filter(
            or_(
                Bien.statut_comptable.in_(["ACTIF", "EN_AMORTISSEMENT"]),
                Bien.statut_comptable.is_(None),
            ),
            ~Bien.id_bien.in_(existing_ids),
        )
        if organisation_id is not None:
            biens_query = biens_query.filter(Bien.organisation_id == organisation_id)

        biens_actifs = biens_query.all()

        resultats = {
            "exercice": exercice,
            "total_biens_traites": len(biens_actifs),
            "amortissements_crees": [],
            "erreurs": [],
        }

        for bien in biens_actifs:
            try:
                data = self._construire_donnees_amortissement(bien, exercice)
                amort = self.creer_amortissement(data, bien.type_bien or "autre")
                resultats["amortissements_crees"].append({
                    "id_amortissement": amort.id_amortissement,
                    "id_bien": bien.id_bien,
                    "annuite_comptable": amort.annuite_comptable,
                })
            except Exception as e:
                resultats["erreurs"].append({
                    "bien_id": bien.id_bien,
                    "erreur": str(e),
                })

        return resultats

    def get_historique_depreciations(self, id_bien: int, organisation_id: Optional[int] = None) -> dict:
        from ..models.ecriture_comptable import EcritureComptable, TypeOperationEnum

        self._check_acces_bien_id(id_bien, organisation_id)

        bien = self.db.query(Bien).filter(Bien.id_bien == id_bien).first()
        if not bien:
            raise ValueError("Bien non trouvé")

        depreciations = (
            self.db.query(Amortissement)
            .filter(
                Amortissement.id_bien == id_bien,
                Amortissement.montant_depreciation > 0,
            )
            .order_by(Amortissement.date_depreciation.desc())
            .all()
        )

        reprises = (
            self.db.query(EcritureComptable)
            .filter(
                EcritureComptable.id_bien == id_bien,
                EcritureComptable.type_operation == TypeOperationEnum.REPRISE_DEPRECIATION,
            )
            .order_by(EcritureComptable.date_ecriture.desc())
            .all()
        )

        return {
            "cumul_depreciation": float(bien.cumul_depreciation or 0),
            "statut_comptable": bien.statut_comptable,
            "depreciations": [
                {
                    "id_amortissement": a.id_amortissement,
                    "date_depreciation": a.date_depreciation.isoformat() if a.date_depreciation else None,
                    "montant_depreciation": float(a.montant_depreciation or 0),
                    "valeur_actualisee": float(a.valeur_actualisee or 0),
                    "exercice": a.exercice,
                }
                for a in depreciations
            ],
            "reprises": [
                {
                    "id_ecriture": e.id_ecriture,
                    "date_ecriture": e.date_ecriture.isoformat() if e.date_ecriture else None,
                    "montant": float(e.montant or 0),
                    "libelle": e.libelle,
                    "compte_debit": e.compte_debit,
                    "compte_credit": e.compte_credit,
                }
                for e in reprises
            ],
        }

    def previsualiser_cloture(
        self, 
        exercice: int, 
        categorie: Optional[str] = None,
        methode_forcee: Optional[str] = None,
        biens_ids: Optional[List[int]] = None,
        organisation_id: Optional[int] = None,
    ) -> dict:
        query = self.db.query(Bien).filter(
            or_(
                Bien.statut_comptable.in_(["ACTIF", "EN_AMORTISSEMENT", "EN_DEPRECIATION"]),
                Bien.statut_comptable.is_(None),
            )
        )
        if organisation_id is not None:
            query = query.filter(Bien.organisation_id == organisation_id)

        if categorie:
            query = query.filter(Bien.type_bien == categorie)

        if biens_ids:
            query = query.filter(Bien.id_bien.in_(biens_ids))

        existing_ids = self.db.query(Amortissement.id_bien).filter(
            Amortissement.exercice == exercice
        )
        query = query.filter(~Bien.id_bien.in_(existing_ids))

        biens = query.all()
        
        biens_preview = []
        total_montant = 0.0
        
        for bien in biens:
            try:
                data = self._construire_donnees_amortissement(bien, exercice, methode_forcee)
                methode_actuelle = data.get("methode") if isinstance(data, dict) else getattr(data, "methode", "LINEAIRE")
                methode_str = methode_actuelle.value if hasattr(methode_actuelle, 'value') else str(methode_actuelle)
                
                regle = self.get_regle_par_categorie(
                    bien.type_bien or "autre",
                    organisation_id=getattr(bien, "organisation_id", None),
                )
                base_amortissable = float(bien.prix_acquisition or 0)
                taux = regle.taux_fiscal if regle else 20.0
                
                annuite_estimee = base_amortissable * (taux / 100)
                
                if methode_forcee == "DEGRESSIF" or (not methode_forcee and methode_str == "DEGRESSIF"):
                    coeff = self.get_coefficient_degressif(regle.duree_vie_ans, regle) if regle else 2.0
                    annuite_estimee = annuite_estimee * coeff
                
                total_montant += annuite_estimee
                
                designation = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
                
                biens_preview.append(BienPrevisualisation(
                    id_bien=bien.id_bien,
                    designation=designation,
                    categorie=bien.type_bien or "autre",
                    methode_actuelle=methode_str,
                    montant_estime=round(annuite_estimee, 2),
                    prix_acquisition=float(bien.prix_acquisition or 0),
                    cumul_amortissement=float(bien.cumul_amortissement or 0),
                    vnc_actuelle=float(bien.prix_acquisition or 0) - float(bien.cumul_amortissement or 0),
                    date_acquisition=bien.date_acquisition,
                    exercice=exercice,
                    est_eligible=True
                ))
            except Exception as e:
                designation = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
                biens_preview.append(BienPrevisualisation(
                    id_bien=bien.id_bien,
                    designation=designation,
                    categorie=bien.type_bien or "autre",
                    methode_actuelle="ERROR",
                    montant_estime=0.0,
                    prix_acquisition=float(bien.prix_acquisition or 0),
                    cumul_amortissement=float(bien.cumul_amortissement or 0),
                    vnc_actuelle=float(bien.prix_acquisition or 0) - float(bien.cumul_amortissement or 0),
                    date_acquisition=bien.date_acquisition,
                    exercice=exercice,
                    est_eligible=False,
                    raison_non_eligibilite=str(e)
                ))

        return {
            "exercice": exercice,
            "total_biens": len(biens_preview),
            "total_eligibles": sum(1 for b in biens_preview if b.est_eligible),
            "total_montant_estime": round(total_montant, 2),
            "biens": biens_preview,
            "filtres_appliques": {
                "categorie": categorie or "toutes",
                "methode_forcee": methode_forcee or "automatique",
                "biens_selectionnes": bool(biens_ids)
            }
        }
    
    def generer_amortissements_massifs_avec_filtres(
        self, 
        exercice: int, 
        categorie: Optional[str] = None,
        methode_forcee: Optional[str] = None,
        biens_ids: Optional[List[int]] = None,
        organisation_id: Optional[int] = None,
    ) -> dict:
        query = self.db.query(Bien).filter(
            or_(
                Bien.statut_comptable.in_(["ACTIF", "EN_AMORTISSEMENT"]),
                Bien.statut_comptable.is_(None),
            )
        )
        if organisation_id is not None:
            query = query.filter(Bien.organisation_id == organisation_id)

        if categorie:
            query = query.filter(Bien.type_bien == categorie)

        if biens_ids:
            query = query.filter(Bien.id_bien.in_(biens_ids))

        existing_ids = self.db.query(Amortissement.id_bien).filter(
            Amortissement.exercice == exercice
        )
        query = query.filter(~Bien.id_bien.in_(existing_ids))

        biens = query.all()

        resultats = {
            "exercice": exercice,
            "total_biens_traites": len(biens),
            "amortissements_crees": [],
            "erreurs": [],
            "resume_par_categorie": {},
            "resume_par_methode": {},
        }

        for bien in biens:
            try:
                data = self._construire_donnees_amortissement(bien, exercice, methode_forcee)
                amort = self.creer_amortissement(data, bien.type_bien or "autre")
                
                resultats["amortissements_crees"].append({
                    "id_amortissement": amort.id_amortissement,
                    "id_bien": bien.id_bien,
                    "annuite_comptable": amort.annuite_comptable,
                    "methode": amort.methode.value if hasattr(amort.methode, 'value') else str(amort.methode),
                    "categorie": bien.type_bien or "autre",
                })
                
                cat = bien.type_bien or "autre"
                if cat not in resultats["resume_par_categorie"]:
                    resultats["resume_par_categorie"][cat] = {"count": 0, "total": 0.0}
                resultats["resume_par_categorie"][cat]["count"] += 1
                resultats["resume_par_categorie"][cat]["total"] += float(amort.annuite_comptable or 0)
                
                meth = amort.methode.value if hasattr(amort.methode, 'value') else str(amort.methode)
                if meth not in resultats["resume_par_methode"]:
                    resultats["resume_par_methode"][meth] = {"count": 0, "total": 0.0}
                resultats["resume_par_methode"][meth]["count"] += 1
                resultats["resume_par_methode"][meth]["total"] += float(amort.annuite_comptable or 0)
                
            except Exception as e:
                resultats["erreurs"].append({
                    "bien_id": bien.id_bien,
                    "designation": f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}",
                    "erreur": str(e),
                })

        for cat in resultats["resume_par_categorie"]:
            resultats["resume_par_categorie"][cat]["total"] = round(resultats["resume_par_categorie"][cat]["total"], 2)
        for meth in resultats["resume_par_methode"]:
            resultats["resume_par_methode"][meth]["total"] = round(resultats["resume_par_methode"][meth]["total"], 2)

        return resultats

    def get_dashboard_data(self, organisation_id: Optional[int] = None) -> dict:
        from ..models.ecriture_comptable import EcritureComptable
        
        annee_courante = datetime.utcnow().year
        
        # Total amortissements comptables pour l'exercice courant
        q_total = self.db.query(func.sum(Amortissement.annuite_comptable)).filter(
            Amortissement.exercice == annee_courante
        )
        if organisation_id is not None:
            q_total = q_total.filter(Amortissement.organisation_id == organisation_id)
        total_amort = q_total.scalar() or 0
        
        if total_amort == 0:
            q_latest = self.db.query(func.max(Amortissement.exercice))
            if organisation_id is not None:
                q_latest = q_latest.filter(Amortissement.organisation_id == organisation_id)
            latest_exercice = q_latest.scalar()
            if latest_exercice:
                q_fallback = self.db.query(func.sum(Amortissement.annuite_comptable)).filter(
                    Amortissement.exercice == latest_exercice
                )
                if organisation_id is not None:
                    q_fallback = q_fallback.filter(Amortissement.organisation_id == organisation_id)
                total_amort = q_fallback.scalar() or 0
        
        # Total écarts fiscaux
        q_ecart = self.db.query(func.sum(Amortissement.ecart_a_reintegrer)).filter(
            Amortissement.exercice == annee_courante
        )
        if organisation_id is not None:
            q_ecart = q_ecart.filter(Amortissement.organisation_id == organisation_id)
        total_ecart = q_ecart.scalar() or 0
        if total_ecart == 0 and total_amort > 0:
            q_latest = self.db.query(func.max(Amortissement.exercice))
            if organisation_id is not None:
                q_latest = q_latest.filter(Amortissement.organisation_id == organisation_id)
            latest_exercice = q_latest.scalar()
            if latest_exercice:
                q_ecart2 = self.db.query(func.sum(Amortissement.ecart_a_reintegrer)).filter(
                    Amortissement.exercice == latest_exercice
                )
                if organisation_id is not None:
                    q_ecart2 = q_ecart2.filter(Amortissement.organisation_id == organisation_id)
                total_ecart = q_ecart2.scalar() or 0

        q_fiscal = self.db.query(func.sum(Amortissement.annuite_fiscale)).filter(
            Amortissement.exercice == annee_courante
        )
        if organisation_id is not None:
            q_fiscal = q_fiscal.filter(Amortissement.organisation_id == organisation_id)
        total_fiscal = q_fiscal.scalar() or 0
        if total_fiscal == 0 and total_amort > 0:
            q_latest = self.db.query(func.max(Amortissement.exercice))
            if organisation_id is not None:
                q_latest = q_latest.filter(Amortissement.organisation_id == organisation_id)
            latest_exercice = q_latest.scalar()
            if latest_exercice:
                q_fiscal2 = self.db.query(func.sum(Amortissement.annuite_fiscale)).filter(
                    Amortissement.exercice == latest_exercice
                )
                if organisation_id is not None:
                    q_fiscal2 = q_fiscal2.filter(Amortissement.organisation_id == organisation_id)
                total_fiscal = q_fiscal2.scalar() or 0
            if total_fiscal == 0:
                total_fiscal = total_amort

        # Biens en fin de vie
        q_biens = self.db.query(Bien).filter(
            Bien.prix_acquisition > 0,
            (Bien.prix_acquisition - Bien.cumul_amortissement) <= Bien.prix_acquisition * 0.10
        )
        if organisation_id is not None:
            q_biens = q_biens.filter(Bien.organisation_id == organisation_id)
        biens_fin_vie_bien = q_biens.count()
        
        q_amorts = self.db.query(Amortissement).filter(
            Amortissement.valeur_nette_comptable <= Amortissement.valeur_origine * 0.10
        )
        if organisation_id is not None:
            q_amorts = q_amorts.filter(Amortissement.organisation_id == organisation_id)
        biens_fin_vie_amort = q_amorts.count()
        
        biens_fin_vie = max(biens_fin_vie_bien, biens_fin_vie_amort)
        
        # Écritures comptables en attente
        q_ecr = self.db.query(EcritureComptable).filter(EcritureComptable.validee == False)
        if organisation_id is not None:
            q_ecr = q_ecr.filter(EcritureComptable.organisation_id == organisation_id)
        ecritures_attente = q_ecr.count()
        
        economie_impot = float(total_fiscal) * 0.30
        
        q_repartition = self.db.query(Bien.type_bien, func.count(Bien.id_bien))
        if organisation_id is not None:
            q_repartition = q_repartition.filter(Bien.organisation_id == organisation_id)
        repartition = q_repartition.group_by(Bien.type_bien).all()
        
        return {
            "total_amortissements_exercice": round(float(total_amort), 2),
            "ecart_fiscal_total": round(float(total_ecart), 2),
            "biens_fin_vie": biens_fin_vie,
            "ecritures_attente_validation": ecritures_attente,
            "economie_impot_annuelle": round(float(economie_impot), 2),
            "repartition_par_categorie": {t: c for t, c in repartition if t},
            "annee_courante": annee_courante
        }

    def fusionner_methodes_okapi_uop(self, bien: Bien, exercice: int, 
                                     unites_consommees: int, 
                                     jours_utilises: int) -> float:
        regle = self.get_regle_par_categorie(
            bien.type_bien or "autre",
            organisation_id=getattr(bien, "organisation_id", None),   # ═══ 5.22 ═══
        )
        
        duree_fournisseur = getattr(bien, 'duree_fournisseur', None) or 5
        unites_totales = getattr(bien, 'unites_totales_prevues', None) or 100000
        jours_ouvres_mois = 26
        
        if unites_totales <= 0:
            return 0.0
        
        base_amortissable = float(bien.prix_acquisition or 0)
        
        amort_okapi = self.calculer_annuite_okapi(
            base_amortissable,
            duree_fournisseur,
            jours_ouvres_mois,
            jours_utilises
        )
        
        amort_uop = self.calculer_annuite_uop(
            base_amortissable,
            unites_consommees,
            unites_totales
        )
        
        annuite_fusionnee = (amort_okapi + amort_uop) / 2
        
        return round(annuite_fusionnee, 2)

    def verrouiller_amortissement(self, id_amortissement: int, verrouille_par: int, raison: str = "Validation exercice", organisation_id: Optional[int] = None) -> Amortissement:
        """
        Verrouille définitivement un amortissement.
        """
        query = self.db.query(Amortissement).filter(
            Amortissement.id_amortissement == id_amortissement
        )
        if organisation_id is not None:
            query = query.filter(Amortissement.organisation_id == organisation_id)
        amortissement = query.first()

        if not amortissement:
            raise ValueError("Amortissement non trouvé")

        if amortissement.est_verrouille:
            raise ValueError("Cet amortissement est déjà verrouillé")

        from ..models.utilisateur import Utilisateur
        utilisateur = self.db.query(Utilisateur).filter(Utilisateur.id == verrouille_par).first()
        if not utilisateur:
            raise ValueError("Utilisateur non trouvé")

        role = utilisateur.role.nom.upper() if utilisateur.role else ""
        if role not in ["DG", "COMPTABLE", "ADMIN"]:
            raise ValueError("Seul le DG, le Comptable ou l'Admin peut verrouiller un amortissement")

        amortissement.verrouiller(verrouille_par, raison)

        try:
            self._generer_ecriture_comptable(amortissement, verrouille_par)
        except Exception as e:
            logger.warning(f"Note lors de la génération d'écriture au verrouillage: {e}")

        self.db.commit()
        self.db.refresh(amortissement)

        from .audit_service import AuditService
        audit = AuditService(self.db)
        audit.log_action(
            user_id=verrouille_par,
            table_name="amortissements",
            record_id=id_amortissement,
            action="VERROUILLAGE",
            nouvelles_valeurs={
                "est_verrouille": True,
                "raison": raison,
                "date_verrouillage": amortissement.date_verrouillage.isoformat() if amortissement.date_verrouillage else None
            }
        )

        return amortissement

    def _generer_ecriture_comptable(self, amortissement: Amortissement, utilisateur_id: int):
        """Génère l'écriture comptable pour l'amortissement."""
        from .comptabilite_service import ComptabiliteService
        comptabilite = ComptabiliteService(self.db)
        bien = self.db.query(Bien).filter(Bien.id_bien == amortissement.id_bien).first()
        
        type_b = getattr(bien, "type_bien", "autre") if bien else "autre"
        if hasattr(type_b, "value"):
            type_b = type_b.value
            
        ecriture = comptabilite.generer_ecriture_dotation(
            amortissement, 
            type_b
        )
        return ecriture

    def calculer_et_verifier_tresorerie(self, id_amortissement: int, organisation_id: Optional[int] = None) -> dict:
        query = self.db.query(Amortissement).filter(
            Amortissement.id_amortissement == id_amortissement
        )
        if organisation_id is not None:
            query = query.filter(Amortissement.organisation_id == organisation_id)
        amortissement = query.first()

        if not amortissement:
            raise ValueError("Amortissement non trouvé")

        montant_dotation = float(amortissement.annuite_comptable or 0)

        from .budget_service import BudgetService
        budget_service = BudgetService(self.db)
        tresorerie = budget_service.verifier_tresorerie(Decimal(str(montant_dotation)), organisation_id=organisation_id)

        return {
            "id_amortissement": amortissement.id_amortissement,
            "montant_dotation": montant_dotation,
            "tresorerie_disponible": float(tresorerie["tresorerie_disponible"]),
            "est_suffisante": tresorerie["est_suffisante"],
            "manque": float(tresorerie["manque"]),
            "recommandation": "Dotation validée" if tresorerie["est_suffisante"] else "Dotation maintenue au compte de charge (Classe 6) en attente de trésorerie"
        }

    def traiter_amortissement_apres_cloture(self, id_amortissement: int, id_validateur: int, organisation_id: Optional[int] = None) -> dict:
        try:
            with self.db.begin():
                query = self.db.query(Amortissement).filter(
                    Amortissement.id_amortissement == id_amortissement
                )
                if organisation_id is not None:
                    query = query.filter(Amortissement.organisation_id == organisation_id)
                amortissement = query.with_for_update().first()

                if not amortissement:
                    raise ValueError("Amortissement non trouvé")

                verif_tresorerie = self.calculer_et_verifier_tresorerie(id_amortissement, organisation_id=organisation_id)

                if not verif_tresorerie["est_suffisante"]:
                    amortissement.statut = StatutAmortissement.SUSPENDU
                    return {
                        "id_amortissement": amortissement.id_amortissement,
                        "statut": amortissement.statut.value,
                        "message": "Trésorerie insuffisante. Montant maintenu au compte de charge.",
                        "manque": verif_tresorerie["manque"]
                    }

                from .comptabilite_service import ComptabiliteService
                comptabilite = ComptabiliteService(self.db, cree_par_id=id_validateur)

                bien = self.db.query(Bien).filter(Bien.id_bien == amortissement.id_bien).first()

                ecriture = comptabilite.generer_ecriture_dotation(amortissement, bien.type_bien if bien else "autre")

                ecriture.validee = True
                ecriture.statut = StatutEcriture.VALIDEE
                ecriture.date_validation = datetime.utcnow()
                ecriture.id_validateur = id_validateur

                self.verrouiller_amortissement(id_amortissement, id_validateur, organisation_id=organisation_id)

        except SQLAlchemyError as e:
            logger.error(f"Erreur traitement amortissement après clôture: {e}")
            raise ValueError(f"Échec du traitement: {str(e)}")

        self.db.refresh(amortissement)
        return {
            "id_amortissement": amortissement.id_amortissement,
            "id_ecriture": ecriture.id_ecriture,
            "statut": amortissement.statut.value,
            "message": "Amortissement validé et écritures générées"
        }

    def previsualiser_cloture_amelioree(self, exercice: int, categorie: Optional[str] = None,
                             methode_forcee: Optional[str] = None,
                             biens_ids: Optional[List[int]] = None,
                             organisation_id: Optional[int] = None) -> dict:
        query = self.db.query(Bien).filter(
            or_(
                Bien.statut_comptable.in_(["ACTIF", "EN_AMORTISSEMENT", "EN_DEPRECIATION"]),
                Bien.statut_comptable.is_(None),
            )
        )
        if organisation_id is not None:
            query = query.filter(Bien.organisation_id == organisation_id)

        if categorie:
            query = query.filter(Bien.type_bien == categorie)

        if biens_ids:
            query = query.filter(Bien.id_bien.in_(biens_ids))

        existing_ids = self.db.query(Amortissement.id_bien).filter(
            Amortissement.exercice == exercice,
            Amortissement.est_verrouille == False
        )
        query = query.filter(~Bien.id_bien.in_(existing_ids))

        biens = query.all()
        
        biens_preview = []
        total_montant = 0.0
        
        for bien in biens:
            try:
                if methode_forcee:
                    methode = MethodeEnum(methode_forcee.upper())
                else:
                    methode = MethodeEnum.LINEAIRE
                
                base_amortissable = float(bien.prix_acquisition or 0)
                regle = self.get_regle_par_categorie(
                    bien.type_bien or "autre",
                    organisation_id=getattr(bien, "organisation_id", None),
                )
                duree = regle.duree_vie_ans if regle else 5
                taux = 100.0 / duree
                
                if methode == MethodeEnum.LINEAIRE:
                    annuite_estimee = base_amortissable * (taux / 100)
                elif methode == MethodeEnum.DEGRESSIF:
                    coeff = self.get_coefficient_degressif(duree, regle) if regle else 2.0
                    annuite_estimee = base_amortissable * (taux / 100) * coeff
                elif methode in [MethodeEnum.UNITE_PRODUCTION, MethodeEnum.SPECIFIQUE_OKAPI]:
                    unites_consommees = getattr(bien, 'unites_consommees', 0) or 0
                    jours_utilises = 260
                    annuite_estimee = self.fusionner_methodes_okapi_uop(
                        bien, exercice, unites_consommees, jours_utilises
                    )
                else:
                    annuite_estimee = base_amortissable * (taux / 100)
                
                total_montant += annuite_estimee
                
                designation = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
                
                biens_preview.append({
                    "id_bien": bien.id_bien,
                    "designation": designation,
                    "categorie": bien.type_bien or "autre",
                    "methode_actuelle": methode.value,
                    "montant_estime": round(annuite_estimee, 2),
                    "prix_acquisition": float(bien.prix_acquisition or 0),
                    "cumul_amortissement": float(bien.cumul_amortissement or 0),
                    "vnc_actuelle": float(bien.valeur_nette_comptable),
                    "date_acquisition": bien.date_acquisition,
                    "exercice": exercice,
                    "est_eligible": True
                })
            except Exception as e:
                designation = f"{getattr(bien, 'marque', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien.id_bien}"
                biens_preview.append({
                    "id_bien": bien.id_bien,
                    "designation": designation,
                    "categorie": bien.type_bien or "autre",
                    "methode_actuelle": "ERROR",
                    "montant_estime": 0.0,
                    "prix_acquisition": float(bien.prix_acquisition or 0),
                    "cumul_amortissement": float(bien.cumul_amortissement or 0),
                    "vnc_actuelle": float(bien.valeur_nette_comptable),
                    "date_acquisition": bien.date_acquisition,
                    "exercice": exercice,
                    "est_eligible": False,
                    "raison_non_eligibilite": str(e)
                })

        return {
            "exercice": exercice,
            "total_biens": len(biens_preview),
            "total_eligibles": sum(1 for b in biens_preview if b["est_eligible"]),
            "total_montant_estime": round(total_montant, 2),
            "biens": biens_preview,
            "filtres_appliques": {
                "categorie": categorie or "toutes",
                "methode_forcee": methode_forcee or "automatique",
                "biens_selectionnes": bool(biens_ids)
            }
        }

    def creer_amortissement_sans_valeur_residuelle(self, data: AmortissementCreate, type_bien: str) -> Amortissement:
        """
        Crée un amortissement sans valeur résiduelle (TÂCHE 2).
        Méthode dédiée pour forcer valeur_residuelle = 0.
        """
        return self.creer_amortissement(data, type_bien)

    # ============================================================
    # MÉTHODES TÂCHE 3
    # ============================================================

    def verifier_seuils_vnc(self, bien_id: int, organisation_id: Optional[int] = None) -> Optional[AlerteVNC]:
        """
        Vérifie si un bien a atteint les seuils d'alerte VNC.
        Seuil critique: 20%, Seuil standard: 5%.
        """
        self._check_acces_bien_id(bien_id, organisation_id)

        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien {bien_id} non trouvé")

        prix_acquisition = float(bien.prix_acquisition) if bien.prix_acquisition else 0
        if prix_acquisition <= 0:
            return None

        vnc = bien.valeur_nette_comptable
        ratio = vnc / prix_acquisition
        ratio_pourcent = ratio * 100

        if bien.est_critique:
            seuil = SEUIL_VNC_CRITIQUE
        else:
            seuil = SEUIL_VNC_STANDARD

        if ratio_pourcent <= seuil:
            alerte_existante = self.db.query(AlerteVNC).filter(
                AlerteVNC.bien_id == bien_id,
                AlerteVNC.seuil_atteint == f"{seuil}%",
                AlerteVNC.statut != StatutAlerteVNC.TRAITEE,
                AlerteVNC.statut != StatutAlerteVNC.ANNULEE
            ).first()

            if not alerte_existante:
                try:
                    with self.db.begin():
                        alerte = AlerteVNC(
                            bien_id=bien_id,
                            seuil_atteint=f"{seuil}%",
                            ratio_vnc=ratio,
                            valeur_vnc=vnc,
                            valeur_origine=prix_acquisition,
                            statut=StatutAlerteVNC.EN_ATTENTE,
                            description=f"Le bien a atteint {seuil}% de sa valeur résiduelle (VNC: {vnc:.2f} USD, Ratio: {ratio_pourcent:.1f}%)",
                            action_recommandee="Planifier le remplacement du bien",
                            organisation_id=getattr(bien, "organisation_id", None),   # ═══ 5.22 ═══
                        )
                        self.db.add(alerte)

                        bien.vnc_alerte_declenchee = True
                        bien.seuil_alerte_atteint = f"{seuil}%"

                except SQLAlchemyError as e:
                    logger.error(f"Erreur création alerte VNC: {e}")
                    return None

                self.db.refresh(alerte)

                self._journaliser_evenement(
                    bien_id=bien_id,
                    type_evenement=TypeEvenementImmobilisation.ALERTE_VNC,
                    libelle=f"Alerte VNC déclenchée - Seuil {seuil}% atteint",
                    montant=vnc,
                    metadonnees=f"Ratio: {ratio_pourcent:.1f}%, Valeur origine: {prix_acquisition:.2f}",
                    organisation_id=getattr(bien, "organisation_id", None),   # ═══ 5.22 ═══
                )

                return alerte

        return None

    def verifier_tous_seuils_vnc(self) -> dict:
        """
        🔴 DÉPRÉCIÉ — Utiliser la tâche CRON cron_alertes_vnc.py
        
        Cette méthode parcourt tous les biens et est trop lourde.
        """
        logger.warning(
            "verifier_tous_seuils_vnc est dépréciée. "
            "Utiliser la tâche CRON pour le calcul batch."
        )
        raise RuntimeError(
            "Méthode dépréciée. Utiliser la tâche de fond cron_alertes_vnc."
        )

    def get_biens_a_verifier_vnc(self, limite: int = 100, organisation_id: Optional[int] = None) -> List[int]:
        """
        Retourne les IDs des biens à vérifier pour les seuils VNC.
        Utilisé par la tâche CRON.
        """
        query = self.db.query(Bien).filter(
            Bien.statut_comptable == 'ACTIF',
            Bien.prix_acquisition.isnot(None),
            Bien.prix_acquisition > 0
        )
        if organisation_id is not None:
            query = query.filter(Bien.organisation_id == organisation_id)
        biens = query.limit(limite).all()

        return [b.id_bien for b in biens]

    def _journaliser_evenement(self, bien_id: int, type_evenement: TypeEvenementImmobilisation, 
                               libelle: str, montant: float = 0.0, 
                               utilisateur_id: int = None, metadonnees: str = None,
                               organisation_id: Optional[int] = None):
        """
        Journalise un événement dans le journal des immobilisations.
        ✅ N'utilise PAS de transaction — appelée hors des blocs with db.begin()
        ✅ En cas d'échec, loggue l'erreur sans lever d'exception
        ✅ 5.22 : injecte organisation_id si fourni
        """
        try:
            journal = JournalEvenementImmobilisation(
                bien_id=bien_id,
                type_evenement=type_evenement,
                date_evenement=datetime.utcnow(),
                libelle=libelle,
                montant=montant,
                utilisateur_id=utilisateur_id,
                metadonnees=metadonnees,
                organisation_id=organisation_id,   # ═══ 5.22 ═══
            )
            self.db.add(journal)
            self.db.commit()
        except Exception as e:
            logger.error(f"Erreur lors de la journalisation: {e}")