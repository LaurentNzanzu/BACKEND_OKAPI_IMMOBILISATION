# backend/app/services/rapport_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract, or_
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date, timedelta
from decimal import Decimal

from ..models.bien import Bien, EtatBien, StatutComptable
from ..models.localisation import Localisation
from ..models.panne import Panne, StatutPanne, TypePanne
from ..models.maintenance import Maintenance, StatutMaintenance, TypeMaintenance, TypeOrigineMaintenance
from ..models.amortissement import Amortissement, MethodeAmortissement
from ..models.ecriture_comptable import EcritureComptable, TypeOperationEnum, StatutEcriture
from ..models.mouvement_bien import MouvementBien, TypeMouvementEnum
from ..models.composant import Composant
from ..models.plan_comptable import PlanComptable
from ..models.fournisseur import Fournisseur
from ..models.cession import Cession
from ..models.alerte_vnc import AlerteVNC, StatutAlerteVNC
from ..models.journal_evenements_immobilisation import JournalEvenementImmobilisation, TypeEvenementImmobilisation
from ..models.projection_investissement import ProjectionInvestissement, StatutProjection

# === NOUVEAUX IMPORTS TÂCHE 3 ===
from ..core.constants import (
    SEUIL_SCORE_BON,
    SEUIL_SCORE_CRITIQUE,
    SEUIL_SCORE_MOYEN,
    SEUIL_VNC_CRITIQUE,
    SEUIL_VNC_STANDARD,
    ANNEE_PROJECTION_DEBUT,
    ANNEE_PROJECTION_FIN,
    TAUX_OBSOLESCENCE_DEFAUT,
    Couleurs
)


class RapportService:
    def __init__(self, db: Session):
        self.db = db

    # ============================================================
    # MÉTHODES UTILITAIRES
    # ============================================================

    def _date_to_datetime(self, d: date) -> datetime:
        """Convertit une date en datetime avec heure 00:00:00"""
        if isinstance(d, datetime):
            return d
        return datetime.combine(d, datetime.min.time())

    def _format_currency(self, value) -> str:
        """Formatte un montant en USD"""
        if value is None:
            return "0,00 USD"
        return f"{float(value):,.2f} USD"

    def _round_value(self, value) -> float:
        """Arrondit une valeur à 2 décimales"""
        if value is None:
            return 0.0
        return round(float(value), 2)

    def _get_bien_designation(self, bien) -> str:
        """Récupère la désignation d'un bien."""
        if not bien:
            return None
        if hasattr(bien, 'marque') and bien.marque:
            return f"{bien.marque} {getattr(bien, 'modele', '')}".strip()
        if hasattr(bien, 'fabricant') and bien.fabricant:
            return f"{bien.fabricant} {getattr(bien, 'modele', '')}".strip()
        return bien.description or f"Bien #{bien.id_bien}"

    def _get_bien_designation_from_id(self, bien_id: int) -> str:
        """Récupère la désignation d'un bien à partir de son ID."""
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        return self._get_bien_designation(bien) if bien else f"Bien #{bien_id}"

    def _get_critere_projection(self, projection: ProjectionInvestissement) -> str:
        """Retourne le critère ayant déclenché la projection."""
        if projection.critere_fin_amortissement:
            return "fin_amortissement"
        elif projection.critere_score_fiabilite:
            return "score_fiabilite"
        elif projection.critere_obligation_legale:
            return "obligation_legale"
        elif projection.critere_remplacement_cyclique:
            return "remplacement_cyclique"
        return "estimation"

    def get_rapport_amortissements(self, annee: int) -> dict:
        """Retourne le rapport détaillé des amortissements pour une année."""
        return self._get_tableau_amortissements(annee)

    def get_rapport_financier(self, date_debut: date, date_fin: date) -> dict:
        """Retourne le rapport financier pour une période."""
        return self.get_rapport_financier_ohada(date_debut, date_fin, date_fin.year)

    def get_rapport_technique(self, date_debut: date, date_fin: date) -> dict:
        """Retourne le rapport technique et de fiabilité des équipements."""
        fiabilite = self.get_rapport_fiabilite()
        maintenances = self.get_rapport_maintenances_preventives()
        return {
            "periode": {"date_debut": str(date_debut), "date_fin": str(date_fin)},
            "fiabilite": fiabilite,
            "maintenances": maintenances
        }

    # ============================================================
    # A. RAPPORT FINANCIER OHADA/SYSCOHADA
    # ============================================================

    def get_rapport_financier_ohada(
        self,
        date_debut: date,
        date_fin: date,
        exercice: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Génère le rapport financier complet conforme aux normes OHADA/SYSCOHADA.
        """
        date_debut_dt = self._date_to_datetime(date_debut)
        date_fin_dt = self._date_to_datetime(date_fin)
        
        if not exercice:
            exercice = date_fin.year

        # A. SYNTHÈSE DU PATRIMOINE IMMOBILIER
        patrimoine = self._get_patrimoine_synthese()

        # B. AMORTISSEMENTS ET DOTATIONS (Note 3C SYSCOHADA)
        amortissements = self._get_amortissements_ohada(exercice)

        # C. CHARGES LIÉES AU CYCLE DE VIE (Pannes, Maintenances)
        charges_cycle_vie = self._get_charges_cycle_vie(date_debut_dt, date_fin_dt)

        # D. CESSIONS ET MOUVEMENTS (Note 3D SYSCOHADA)
        cessions_mouvements = self._get_cessions_mouvements(date_debut_dt, date_fin_dt)

        # E. TABLEAU DE SUIVI DES AMORTISSEMENTS (Note 3C)
        tableau_amortissements = self._get_tableau_amortissements(exercice)

        # F. NOTES ANNEXES SYSCOHADA
        notes_annexes = self._get_notes_annexes_ohada(exercice)

        return {
            "periode": {
                "debut": date_debut.strftime("%d/%m/%Y"),
                "fin": date_fin.strftime("%d/%m/%Y"),
                "exercice": exercice
            },
            "patrimoine": patrimoine,
            "amortissements": amortissements,
            "charges_cycle_vie": charges_cycle_vie,
            "cessions_mouvements": cessions_mouvements,
            "tableau_amortissements": tableau_amortissements,
            "notes_annexes": notes_annexes,
            "date_generation": datetime.now().strftime("%d/%m/%Y %H:%M")
        }

    # ============================================================
    # A. SYNTHÈSE DU PATRIMOINE IMMOBILIER
    # ============================================================

    def _get_patrimoine_synthese(self) -> Dict[str, Any]:
        """Synthèse du patrimoine immobilier"""
        
        # Valeur totale d'acquisition
        valeur_totale = self.db.query(func.sum(Bien.prix_acquisition)).scalar() or 0
        
        # Nombre total de biens
        total_biens = self.db.query(func.count(Bien.id_bien)).scalar() or 0
        
        # Répartition par type de bien
        repartition_type = self.db.query(
            Bien.type_bien,
            func.count(Bien.id_bien).label('count'),
            func.sum(Bien.prix_acquisition).label('valeur')
        ).group_by(Bien.type_bien).all()
        
        repartition_type_dict = {
            t.type_bien or "autre": {
                "count": t.count,
                "valeur": float(t.valeur) if t.valeur else 0
            }
            for t in repartition_type
        }
        
        # Répartition par état
        repartition_etat = self.db.query(
            Bien.etat,
            func.count(Bien.id_bien).label('count')
        ).group_by(Bien.etat).all()
        
        repartition_etat_dict = {
            e.etat.value if e.etat else "INCONNU": e.count
            for e in repartition_etat
        }
        
        # Répartition par statut comptable
        repartition_statut = self.db.query(
            Bien.statut_comptable,
            func.count(Bien.id_bien).label('count')
        ).group_by(Bien.statut_comptable).all()
        
        repartition_statut_dict = {
            s.statut_comptable or "INCONNU": s.count
            for s in repartition_statut
        }
        
        # Biens par fournisseur (top 10)
        top_fournisseurs = self.db.query(
            Fournisseur.nom,
            func.count(Bien.id_bien).label('count'),
            func.sum(Bien.prix_acquisition).label('valeur')
        ).join(Bien, Bien.fournisseur_id == Fournisseur.id).group_by(
            Fournisseur.id, Fournisseur.nom
        ).order_by(func.sum(Bien.prix_acquisition).desc()).limit(10).all()
        
        top_fournisseurs_list = [
            {
                "nom": f.nom,
                "count": f.count,
                "valeur": float(f.valeur) if f.valeur else 0
            }
            for f in top_fournisseurs
        ]
        
        return {
            "valeur_totale_acquisition": self._round_value(valeur_totale),
            "total_biens": total_biens,
            "repartition_par_type": repartition_type_dict,
            "repartition_par_etat": repartition_etat_dict,
            "repartition_par_statut_comptable": repartition_statut_dict,
            "top_fournisseurs": top_fournisseurs_list
        }

    # ============================================================
    # B. AMORTISSEMENTS ET DOTATIONS (Note 3C SYSCOHADA)
    # ============================================================

    def _get_amortissements_ohada(self, exercice: int) -> Dict[str, Any]:
        """Amortissements et dotations conformes à la Note 3C"""
        
        # Dotations de l'exercice (compte 68)
        dotations = self.db.query(
            func.sum(Amortissement.annuite_comptable)
        ).filter(
            Amortissement.exercice == exercice,
            Amortissement.statut == "EN_COURS"
        ).scalar() or 0
        
        # Cumul total des amortissements
        cumul_total = self.db.query(
            func.sum(Bien.cumul_amortissement)
        ).scalar() or 0
        
        # Valeur nette comptable totale (VNC)
        vnc_total = self.db.query(
            func.sum(Bien.prix_acquisition - Bien.cumul_amortissement)
        ).scalar() or 0
        
        # Détail par méthode d'amortissement
        detail_methode = self.db.query(
            Amortissement.methode,
            func.count(Amortissement.id_amortissement).label('count'),
            func.sum(Amortissement.annuite_comptable).label('dotation'),
            func.sum(Amortissement.cumul_comptable).label('cumul')
        ).filter(
            Amortissement.exercice == exercice
        ).group_by(Amortissement.methode).all()
        
        detail_methode_dict = {
            m.methode.value if m.methode else "INCONNU": {
                "count": m.count,
                "dotation": self._round_value(m.dotation),
                "cumul": self._round_value(m.cumul)
            }
            for m in detail_methode
        }
        
        # Détail par catégorie de bien
        detail_categorie = self.db.query(
            Bien.type_bien,
            func.count(Amortissement.id_amortissement).label('count'),
            func.sum(Amortissement.annuite_comptable).label('dotation'),
            func.sum(Amortissement.cumul_comptable).label('cumul'),
            func.sum(Bien.prix_acquisition).label('valeur_brute')
        ).join(Bien, Amortissement.id_bien == Bien.id_bien).filter(
            Amortissement.exercice == exercice
        ).group_by(Bien.type_bien).all()
        
        detail_categorie_dict = {
            c.type_bien or "autre": {
                "count": c.count,
                "dotation": self._round_value(c.dotation),
                "cumul": self._round_value(c.cumul),
                "valeur_brute": self._round_value(c.valeur_brute),
                "vnc": self._round_value(float(c.valeur_brute or 0) - float(c.cumul or 0))
            }
            for c in detail_categorie
        }
        
        return {
            "exercice": exercice,
            "dotations_exercice": self._round_value(dotations),
            "cumul_total_amortissements": self._round_value(cumul_total),
            "valeur_nette_comptable_totale": self._round_value(vnc_total),
            "detail_par_methode": detail_methode_dict,
            "detail_par_categorie": detail_categorie_dict
        }

    # ============================================================
    # C. CHARGES LIÉES AU CYCLE DE VIE
    # ============================================================

    def _get_charges_cycle_vie(self, date_debut: datetime, date_fin: datetime) -> Dict[str, Any]:
        """Charges liées aux pannes et maintenances"""
        
        # Coût total des pannes terminées
        cout_pannes = self.db.query(
            func.sum(Panne.cout_total_reparation)
        ).filter(
            Panne.date_declaration >= date_debut,
            Panne.date_declaration <= date_fin,
            Panne.statut == StatutPanne.TERMINEE
        ).scalar() or 0
        
        # Nombre de pannes
        nb_pannes = self.db.query(
            func.count(Panne.id_panne)
        ).filter(
            Panne.date_declaration >= date_debut,
            Panne.date_declaration <= date_fin
        ).scalar() or 0
        
        # Pannes par type
        pannes_par_type = self.db.query(
            Panne.type_panne,
            func.count(Panne.id_panne).label('count'),
            func.sum(Panne.cout_total_reparation).label('cout')
        ).filter(
            Panne.date_declaration >= date_debut,
            Panne.date_declaration <= date_fin,
            Panne.statut == StatutPanne.TERMINEE
        ).group_by(Panne.type_panne).all()
        
        pannes_par_type_dict = {
            p.type_panne.value if p.type_panne else "AUTRE": {
                "count": p.count,
                "cout": self._round_value(p.cout)
            }
            for p in pannes_par_type
        }
        
        # Coût total des maintenances terminées
        cout_maintenances = self.db.query(
            func.sum(Maintenance.cout)
        ).filter(
            Maintenance.date_debut_reelle >= date_debut,
            Maintenance.date_debut_reelle <= date_fin,
            Maintenance.statut == StatutMaintenance.TERMINEE
        ).scalar() or 0
        
        # Nombre de maintenances
        nb_maintenances = self.db.query(
            func.count(Maintenance.id_maintenance)
        ).filter(
            Maintenance.date_debut_reelle >= date_debut,
            Maintenance.date_debut_reelle <= date_fin
        ).scalar() or 0
        
        # Maintenances par type
        maintenances_par_type = self.db.query(
            Maintenance.type_maintenance,
            func.count(Maintenance.id_maintenance).label('count'),
            func.sum(Maintenance.cout).label('cout')
        ).filter(
            Maintenance.date_debut_reelle >= date_debut,
            Maintenance.date_debut_reelle <= date_fin,
            Maintenance.statut == StatutMaintenance.TERMINEE
        ).group_by(Maintenance.type_maintenance).all()
        
        maintenances_par_type_dict = {
            m.type_maintenance.value if m.type_maintenance else "AUTRE": {
                "count": m.count,
                "cout": self._round_value(m.cout)
            }
            for m in maintenances_par_type
        }
        
        # Top 5 biens les plus coûteux en maintenance + pannes
        top_biens_cout = self.db.query(
            Bien.id_bien,
            Bien.qr_code,
            Bien.type_bien,
            Localisation.nom_localisation.label("localisation"),
            func.sum(Panne.cout_total_reparation).label('cout_pannes'),
            func.sum(Maintenance.cout).label('cout_maintenances')
        ).outerjoin(Panne, Panne.id_bien == Bien.id_bien).outerjoin(
            Localisation, Bien.id_localisation == Localisation.id_localisation
        ).outerjoin(
            Maintenance, Maintenance.id_bien == Bien.id_bien
        ).filter(
            or_(
                Panne.date_declaration.between(date_debut, date_fin),
                Maintenance.date_debut_reelle.between(date_debut, date_fin)
            )
        ).group_by(Bien.id_bien, Bien.qr_code, Bien.type_bien, Localisation.nom_localisation).order_by(
            (func.coalesce(func.sum(Panne.cout_total_reparation), 0) + 
             func.coalesce(func.sum(Maintenance.cout), 0)).desc()
        ).limit(5).all()
        
        top_biens_list = [
            {
                "id_bien": b.id_bien,
                "qr_code": b.qr_code,
                "designation": f"{b.type_bien or ''} - {b.localisation or ''}".strip() or f"Bien #{b.id_bien}",
                "cout_pannes": self._round_value(b.cout_pannes),
                "cout_maintenances": self._round_value(b.cout_maintenances),
                "cout_total": self._round_value((b.cout_pannes or 0) + (b.cout_maintenances or 0))
            }
            for b in top_biens_cout
        ]
        
        return {
            "pannes": {
                "total": nb_pannes,
                "cout_total": self._round_value(cout_pannes),
                "par_type": pannes_par_type_dict
            },
            "maintenances": {
                "total": nb_maintenances,
                "cout_total": self._round_value(cout_maintenances),
                "par_type": maintenances_par_type_dict
            },
            "total_charges": self._round_value(cout_pannes + cout_maintenances),
            "top_biens_cout": top_biens_list
        }

    # ============================================================
    # D. CESSIONS ET MOUVEMENTS (Note 3D SYSCOHADA)
    # ============================================================

    def _get_cessions_mouvements(self, date_debut: datetime, date_fin: datetime) -> Dict[str, Any]:
        """Cessions et mouvements conformes à la Note 3D"""
        
        # Cessions enregistrées
        cessions = self.db.query(
            Cession.id_cession,
            Cession.id_bien,
            Cession.date_cession,
            Cession.prix_vente,
            Cession.acheteur,
            Cession.type_cession,
            Cession.resultat,
            Bien.qr_code,
            Bien.type_bien,
            Localisation.nom_localisation.label("localisation"),
            Bien.prix_acquisition,
            Bien.cumul_amortissement
        ).join(Bien, Cession.id_bien == Bien.id_bien).outerjoin(
            Localisation, Bien.id_localisation == Localisation.id_localisation
        ).filter(
            Cession.date_cession >= date_debut.date(),
            Cession.date_cession <= date_fin.date()
        ).all()
        
        total_cessions = len(cessions)
        total_prix_vente = sum(float(c.prix_vente or 0) for c in cessions)
        total_vnc = sum(
            float(c.prix_acquisition or 0) - float(c.cumul_amortissement or 0)
            for c in cessions
        )
        total_resultat = sum(float(c.resultat or 0) for c in cessions)
        
        details_cessions = []
        plus_values = 0
        moins_values = 0
        
        for c in cessions:
            vnc = float(c.prix_acquisition or 0) - float(c.cumul_amortissement or 0)
            prix_vente = float(c.prix_vente or 0)
            resultat = prix_vente - vnc
            
            if resultat > 0:
                plus_values += resultat
            else:
                moins_values += abs(resultat)
            
            details_cessions.append({
                "id_cession": c.id_cession,
                "id_bien": c.id_bien,
                "qr_code": c.qr_code,
                "designation": f"{c.type_bien or ''} - {c.localisation or ''}".strip() or f"Bien #{c.id_bien}",
                "date_cession": c.date_cession.strftime("%d/%m/%Y") if c.date_cession else "",
                "valeur_acquisition": self._round_value(c.prix_acquisition),
                "cumul_amortissement": self._round_value(c.cumul_amortissement),
                "vnc": self._round_value(vnc),
                "prix_vente": self._round_value(prix_vente),
                "type_cession": c.type_cession or "courante",
                "acheteur": c.acheteur or "",
                "resultat": self._round_value(resultat)
            })
        
        # Mouvements de transfert
        mouvements = self.db.query(
            MouvementBien.id_mouvement,
            MouvementBien.id_bien,
            MouvementBien.type_mouvement,
            MouvementBien.date_mouvement,
            MouvementBien.localisation_source,
            MouvementBien.localisation_destination,
            MouvementBien.raison,
            Bien.qr_code,
            Bien.type_bien,
            Localisation.nom_localisation.label("localisation")
        ).join(Bien, MouvementBien.id_bien == Bien.id_bien).outerjoin(
            Localisation, Bien.id_localisation == Localisation.id_localisation
        ).filter(
            MouvementBien.date_mouvement >= date_debut,
            MouvementBien.date_mouvement <= date_fin,
            MouvementBien.type_mouvement == TypeMouvementEnum.TRANSFERT
        ).all()
        
        details_mouvements = [
            {
                "id_mouvement": m.id_mouvement,
                "id_bien": m.id_bien,
                "qr_code": m.qr_code,
                "designation": f"{m.type_bien or ''} - {m.localisation or ''}".strip() or f"Bien #{m.id_bien}",
                "date_mouvement": m.date_mouvement.strftime("%d/%m/%Y") if m.date_mouvement else "",
                "type": m.type_mouvement.value if m.type_mouvement else "",
                "source": m.localisation_source or "",
                "destination": m.localisation_destination or "",
                "raison": m.raison or ""
            }
            for m in mouvements
        ]
        
        # Biens mis au rebut (statut comptable)
        rebuts = self.db.query(
            Bien.id_bien,
            Bien.qr_code,
            Bien.type_bien,
            Localisation.nom_localisation.label("localisation"),
            Bien.prix_acquisition,
            Bien.cumul_amortissement,
            Bien.date_sortie
        ).outerjoin(
            Localisation, Bien.id_localisation == Localisation.id_localisation
        ).filter(
            Bien.statut_comptable == "MIS_AU_REBUT",
            Bien.date_sortie >= date_debut,
            Bien.date_sortie <= date_fin
        ).all()
        
        details_rebuts = [
            {
                "id_bien": r.id_bien,
                "qr_code": r.qr_code,
                "designation": f"{r.type_bien or ''} - {r.localisation or ''}".strip() or f"Bien #{r.id_bien}",
                "valeur_acquisition": self._round_value(r.prix_acquisition),
                "cumul_amortissement": self._round_value(r.cumul_amortissement),
                "vnc": self._round_value((r.prix_acquisition or 0) - (r.cumul_amortissement or 0)),
                "date_sortie": r.date_sortie.strftime("%d/%m/%Y") if r.date_sortie else ""
            }
            for r in rebuts
        ]
        
        return {
            "total_cessions": total_cessions,
            "total_prix_vente": self._round_value(total_prix_vente),
            "total_vnc_cedee": self._round_value(total_vnc),
            "total_resultat": self._round_value(total_resultat),
            "plus_values": self._round_value(plus_values),
            "moins_values": self._round_value(moins_values),
            "details_cessions": details_cessions,
            "total_mouvements": len(mouvements),
            "details_mouvements": details_mouvements,
            "total_rebuts": len(rebuts),
            "details_rebuts": details_rebuts
        }

    # ============================================================
    # E. TABLEAU DE SUIVI DES AMORTISSEMENTS (Note 3C SYSCOHADA)
    # ============================================================

    def _get_tableau_amortissements(self, exercice: int) -> Dict[str, Any]:
        """Tableau de suivi des amortissements conforme à la Note 3C"""
        
        amortissements = self.db.query(
            Amortissement.id_amortissement,
            Amortissement.id_bien,
            Amortissement.exercice,
            Amortissement.methode,
            Amortissement.duree_vie_comptable_ans,
            Amortissement.taux_comptable,
            Amortissement.valeur_origine,
            Amortissement.valeur_residuelle,
            Amortissement.annuite_comptable,
            Amortissement.cumul_comptable,
            Amortissement.valeur_nette_comptable,
            Bien.qr_code,
            Bien.type_bien,
            Localisation.nom_localisation.label("localisation"),
            Bien.date_acquisition
        ).join(Bien, Amortissement.id_bien == Bien.id_bien).outerjoin(
            Localisation, Bien.id_localisation == Localisation.id_localisation
        ).filter(
            Amortissement.exercice == exercice,
            Amortissement.statut == "EN_COURS"
        ).all()
        
        details = []
        total_valeur_origine = 0
        total_annuite = 0
        total_cumul = 0
        total_vnc = 0
        
        for a in amortissements:
            valeur_origine = self._round_value(a.valeur_origine)
            annuite = self._round_value(a.annuite_comptable)
            cumul = self._round_value(a.cumul_comptable)
            vnc = self._round_value(a.valeur_nette_comptable)
            
            total_valeur_origine += valeur_origine
            total_annuite += annuite
            total_cumul += cumul
            total_vnc += vnc
            
            details.append({
                "id_bien": a.id_bien,
                "qr_code": a.qr_code,
                "designation": f"{a.type_bien or ''} - {a.localisation or ''}".strip() or f"Bien #{a.id_bien}",
                "type_bien": a.type_bien or "",
                "date_acquisition": a.date_acquisition.strftime("%d/%m/%Y") if a.date_acquisition else "",
                "methode": a.methode.value if a.methode else "LINEAIRE",
                "duree_vie": a.duree_vie_comptable_ans or 0,
                "taux": self._round_value(a.taux_comptable),
                "valeur_origine": valeur_origine,
                "valeur_residuelle": self._round_value(a.valeur_residuelle),
                "annuite_exercice": annuite,
                "cumul_amortissements": cumul,
                "valeur_nette_comptable": vnc
            })
        
        # Regroupement par catégorie pour le résumé
        regroupement = {}
        for d in details:
            cat = d["type_bien"] or "autre"
            if cat not in regroupement:
                regroupement[cat] = {
                    "count": 0,
                    "valeur_origine": 0,
                    "annuite": 0,
                    "cumul": 0,
                    "vnc": 0
                }
            regroupement[cat]["count"] += 1
            regroupement[cat]["valeur_origine"] += d["valeur_origine"]
            regroupement[cat]["annuite"] += d["annuite_exercice"]
            regroupement[cat]["cumul"] += d["cumul_amortissements"]
            regroupement[cat]["vnc"] += d["valeur_nette_comptable"]
        
        # Arrondir les regroupements
        for cat in regroupement:
            regroupement[cat]["valeur_origine"] = self._round_value(regroupement[cat]["valeur_origine"])
            regroupement[cat]["annuite"] = self._round_value(regroupement[cat]["annuite"])
            regroupement[cat]["cumul"] = self._round_value(regroupement[cat]["cumul"])
            regroupement[cat]["vnc"] = self._round_value(regroupement[cat]["vnc"])
        
        return {
            "exercice": exercice,
            "total_biens": len(details),
            "total_valeur_origine": self._round_value(total_valeur_origine),
            "total_annuite_exercice": self._round_value(total_annuite),
            "total_cumul_amortissements": self._round_value(total_cumul),
            "total_valeur_nette_comptable": self._round_value(total_vnc),
            "regroupement_par_categorie": regroupement,
            "details": details
        }

    # ============================================================
    # F. NOTES ANNEXES SYSCOHADA
    # ============================================================

    def _get_notes_annexes_ohada(self, exercice: int) -> Dict[str, Any]:
        """Notes annexes conformes au SYSCOHADA"""
        
        # Note 3A : Immobilisations brutes
        immobilisations_brutes = self.db.query(
            Bien.type_bien,
            func.sum(Bien.prix_acquisition).label('valeur_brute'),
            func.count(Bien.id_bien).label('count')
        ).group_by(Bien.type_bien).all()
        
        note_3a = {
            "titre": "Note 3A - Immobilisations brutes",
            "details": [
                {
                    "categorie": ib.type_bien or "autre",
                    "valeur_brute": self._round_value(ib.valeur_brute),
                    "nombre_biens": ib.count
                }
                for ib in immobilisations_brutes
            ]
        }
        
        # Note 3C : Amortissements (déjà calculé)
        amortissements_data = self.db.query(
            func.sum(Amortissement.annuite_comptable).label('dotation'),
            func.sum(Amortissement.cumul_comptable).label('cumul')
        ).filter(
            Amortissement.exercice == exercice
        ).first()
        
        note_3c = {
            "titre": "Note 3C - Amortissements",
            "details": {
                "dotation_exercice": self._round_value(amortissements_data.dotation or 0),
                "cumul_amortissements": self._round_value(amortissements_data.cumul or 0)
            }
        }
        
        # Note 3D : Plus/moins-values de cession (déjà calculé dans cessions)
        cessions = self.db.query(
            Cession.resultat
        ).all()
        
        plus_values = sum(float(c.resultat or 0) for c in cessions if float(c.resultat or 0) > 0)
        moins_values = sum(abs(float(c.resultat or 0)) for c in cessions if float(c.resultat or 0) < 0)
        
        note_3d = {
            "titre": "Note 3D - Plus/moins-values de cession",
            "details": {
                "plus_values": self._round_value(plus_values),
                "moins_values": self._round_value(moins_values),
                "resultat_net": self._round_value(plus_values - moins_values)
            }
        }
        
        # Note 3B : Location-acquisition (si applicable)
        note_3b = {
            "titre": "Note 3B - Location-acquisition",
            "details": {
                "nombre_contrats": 0,
                "valeur_totale": 0,
                "commentaire": "Aucun contrat de location-acquisition en cours"
            }
        }
        
        return {
            "note_3a": note_3a,
            "note_3b": note_3b,
            "note_3c": note_3c,
            "note_3d": note_3d
        }

    # ============================================================
    # G. TABLEAU 8 OHADA (CORRIGÉ)
    # ============================================================

    def generer_tableau8_ohada(self, annee: int) -> dict:
        """
        Génère le Tableau 8 OHADA pour une année donnée
        """
        # ✅ CORRECTION : Utiliser date() au lieu de datetime()
        debut_annee = date(annee, 1, 1)
        fin_annee = date(annee, 12, 31)
        
        biens = self.db.query(Bien).filter(
            Bien.date_acquisition <= fin_annee,
            (Bien.date_sortie.is_(None) | (Bien.date_sortie >= debut_annee))
        ).all()
        
        categories = {}
        for bien in biens:
            categorie = bien.type_bien or "autre"
            if categorie not in categories:
                categories[categorie] = {
                    "brut_debut": 0.0,
                    "augmentations": 0.0,
                    "diminutions": 0.0,
                    "brut_fin": 0.0,
                    "amortissements_cumules": 0.0,
                    "vnc_fin": 0.0,
                    "dotations_exercice": 0.0,
                    "nombre_biens": 0
                }
            
            categories[categorie]["nombre_biens"] += 1
            prix = float(bien.prix_acquisition or 0)
            
            # ✅ Vérification que date_acquisition n'est pas None
            if bien.date_acquisition and bien.date_acquisition < debut_annee:
                categories[categorie]["brut_debut"] += prix
            
            if bien.date_acquisition and bien.date_acquisition >= debut_annee:
                categories[categorie]["augmentations"] += prix
            
            if bien.date_sortie and bien.date_sortie >= debut_annee:
                categories[categorie]["diminutions"] += prix
            
            cumul = float(bien.cumul_amortissement or 0)
            categories[categorie]["amortissements_cumules"] += cumul
            
            vnc_fin = prix - cumul
            categories[categorie]["vnc_fin"] += vnc_fin
            
            dotation = self.db.query(
                func.sum(Amortissement.annuite_comptable)
            ).filter(
                Amortissement.id_bien == bien.id_bien,
                Amortissement.exercice == annee
            ).scalar() or 0
            categories[categorie]["dotations_exercice"] += float(dotation)
        
        total_brut_debut = 0.0
        total_augmentations = 0.0
        total_diminutions = 0.0
        total_brut_fin = 0.0
        total_amortissements = 0.0
        total_vnc_fin = 0.0
        total_dotations = 0.0
        
        for cat in categories.values():
            cat["brut_fin"] = self._round_value(cat["brut_debut"] + cat["augmentations"] - cat["diminutions"])
            cat["brut_debut"] = self._round_value(cat["brut_debut"])
            cat["augmentations"] = self._round_value(cat["augmentations"])
            cat["diminutions"] = self._round_value(cat["diminutions"])
            cat["amortissements_cumules"] = self._round_value(cat["amortissements_cumules"])
            cat["vnc_fin"] = self._round_value(cat["vnc_fin"])
            cat["dotations_exercice"] = self._round_value(cat["dotations_exercice"])
            
            total_brut_debut += cat["brut_debut"]
            total_augmentations += cat["augmentations"]
            total_diminutions += cat["diminutions"]
            total_brut_fin += cat["brut_fin"]
            total_amortissements += cat["amortissements_cumules"]
            total_vnc_fin += cat["vnc_fin"]
            total_dotations += cat["dotations_exercice"]
        
        coherent, ecart = self._verifier_equilibrage_tableau8(annee, total_dotations)
        
        mouvements = self.db.query(
            MouvementBien.id_mouvement,
            MouvementBien.id_bien,
            MouvementBien.type_mouvement,
            MouvementBien.date_mouvement,
            MouvementBien.localisation_source,
            MouvementBien.localisation_destination,
            Bien.qr_code,
            Bien.type_bien
        ).join(Bien, MouvementBien.id_bien == Bien.id_bien).filter(
            MouvementBien.date_mouvement >= debut_annee,
            MouvementBien.date_mouvement <= fin_annee
        ).all()
        
        details_mouvements = [
            {
                "id_mouvement": m.id_mouvement,
                "id_bien": m.id_bien,
                "qr_code": m.qr_code,
                "designation": m.type_bien or f"Bien #{m.id_bien}",
                "date_mouvement": m.date_mouvement.strftime("%d/%m/%Y") if m.date_mouvement else "",
                "type": m.type_mouvement.value if m.type_mouvement else "",
                "source": m.localisation_source or "",
                "destination": m.localisation_destination or ""
            }
            for m in mouvements
        ]
        
        return {
            "annee": annee,
            "categories": categories,
            "total_general": {
                "brut_debut": self._round_value(total_brut_debut),
                "augmentations": self._round_value(total_augmentations),
                "diminutions": self._round_value(total_diminutions),
                "brut_fin": self._round_value(total_brut_fin),
                "amortissements_cumules": self._round_value(total_amortissements),
                "vnc_fin": self._round_value(total_vnc_fin),
                "dotations_exercice": self._round_value(total_dotations),
                "nombre_total_biens": len(biens)
            },
            "mouvements": {
                "total": len(mouvements),
                "details": details_mouvements
            },
            "coherent": coherent,
            "ecart": round(ecart, 2) if not coherent else None
        }

    def _verifier_equilibrage_tableau8(self, annee: int, total_dotations_tableau: float) -> tuple:
        """
        Vérifie que le Tableau 8 est cohérent avec le Grand Livre
        """
        # ✅ CORRECTION : Utiliser date() au lieu de datetime()
        debut_annee = date(annee, 1, 1)
        fin_annee = date(annee, 12, 31)
        
        total_dotations_livre = self.db.query(
            func.sum(EcritureComptable.montant)
        ).filter(
            EcritureComptable.compte_debit == "6812",
            EcritureComptable.date_ecriture >= debut_annee,
            EcritureComptable.date_ecriture <= fin_annee,
            EcritureComptable.statut == StatutEcriture.VALIDEE
        ).scalar() or 0
        
        ecart = abs(float(total_dotations_tableau or 0) - float(total_dotations_livre or 0))
        coherent = ecart < 0.01
        
        return coherent, ecart

    # ============================================================
    # H. ALERTES VNC
    # ============================================================

    def get_synthese_alertes_vnc(self) -> dict:
        """
        Récupère la synthèse des alertes VNC pour le tableau de bord
        """
        alertes_attente = self.db.query(AlerteVNC).filter(
            AlerteVNC.statut == StatutAlerteVNC.EN_ATTENTE
        ).count()
        
        alertes_cours = self.db.query(AlerteVNC).filter(
            AlerteVNC.statut == StatutAlerteVNC.EN_COURS
        ).count()
        
        alertes_traitees = self.db.query(AlerteVNC).filter(
            AlerteVNC.statut == StatutAlerteVNC.TRAITEE
        ).count()
        
        biens_critiques_alerte = self.db.query(Bien).filter(
            Bien.est_critique == True,
            Bien.vnc_alerte_declenchee == True,
            Bien.statut_comptable == 'ACTIF'
        ).count()
        
        alertes_recentes = self.db.query(
            AlerteVNC.id,
            AlerteVNC.bien_id,
            AlerteVNC.seuil_atteint,
            AlerteVNC.ratio_vnc,
            AlerteVNC.valeur_vnc,
            AlerteVNC.date_alerte,
            AlerteVNC.statut,
            Bien.qr_code,
            Bien.type_bien,
            Bien.prix_acquisition
        ).join(Bien, AlerteVNC.bien_id == Bien.id_bien).order_by(
            AlerteVNC.date_alerte.desc()
        ).limit(10).all()
        
        details_recentes = [
            {
                "id": a.id,
                "bien_id": a.bien_id,
                "qr_code": a.qr_code,
                "designation": a.type_bien or f"Bien #{a.bien_id}",
                "seuil_atteint": a.seuil_atteint,
                "ratio_vnc": self._round_value(a.ratio_vnc * 100),
                "valeur_vnc": self._round_value(a.valeur_vnc),
                "valeur_origine": self._round_value(a.prix_acquisition),
                "date_alerte": a.date_alerte.strftime("%d/%m/%Y %H:%M") if a.date_alerte else "",
                "statut": a.statut.value if a.statut else ""
            }
            for a in alertes_recentes
        ]
        
        return {
            "total_alertes": alertes_attente + alertes_cours + alertes_traitees,
            "en_attente": alertes_attente,
            "en_cours": alertes_cours,
            "traitees": alertes_traitees,
            "biens_critiques_avec_alerte": biens_critiques_alerte,
            "alertes_recentes": details_recentes,
            "seuils": {
                "critique": SEUIL_VNC_CRITIQUE,
                "standard": SEUIL_VNC_STANDARD
            }
        }

    # ============================================================
    # I. RAPPORT DE FIABILITÉ
    # ============================================================

    def get_rapport_fiabilite(self) -> dict:
        """
        Génère un rapport sur la fiabilité des biens
        """
        biens = self.db.query(Bien).filter(
            Bien.statut_comptable == 'ACTIF'
        ).all()
        
        total_biens = len(biens)
        biens_avec_score = [b for b in biens if b.score_fiabilite is not None]
        total_avec_score = len(biens_avec_score)
        
        critique = [b for b in biens_avec_score if b.score_fiabilite < SEUIL_SCORE_CRITIQUE]
        moyen = [b for b in biens_avec_score if SEUIL_SCORE_CRITIQUE <= b.score_fiabilite < SEUIL_SCORE_MOYEN]
        bon = [b for b in biens_avec_score if b.score_fiabilite >= SEUIL_SCORE_MOYEN]
        
        if total_avec_score > 0:
            score_moyen = sum(b.score_fiabilite for b in biens_avec_score) / total_avec_score
        else:
            score_moyen = 0
        
        biens_critiques_faible = [b for b in biens if b.est_critique and b.score_fiabilite is not None and b.score_fiabilite < SEUIL_SCORE_CRITIQUE]
        
        details_faible = [
            {
                "id_bien": b.id_bien,
                "qr_code": b.qr_code,
                "designation": b.type_bien or f"Bien #{b.id_bien}",
                "score_fiabilite": self._round_value(b.score_fiabilite),
                "est_critique": b.est_critique,
                "nb_pannes": self.db.query(func.count(Panne.id_panne)).filter(
                    Panne.id_bien == b.id_bien,
                    Panne.statut == StatutPanne.TERMINEE
                ).scalar() or 0,
                "couleur": Couleurs.SCORE_CRITIQUE if b.score_fiabilite < SEUIL_SCORE_CRITIQUE 
                           else Couleurs.SCORE_MOYEN if b.score_fiabilite < SEUIL_SCORE_MOYEN 
                           else Couleurs.SCORE_BON
            }
            for b in biens_avec_score
            if b.score_fiabilite < SEUIL_SCORE_MOYEN
        ]
        
        return {
            "total_biens": total_biens,
            "total_avec_score": total_avec_score,
            "score_moyen": self._round_value(score_moyen),
            "repartition": {
                "critique": len(critique),
                "moyen": len(moyen),
                "bon": len(bon)
            },
            "pourcentages": {
                "critique": round(len(critique) / total_avec_score * 100, 1) if total_avec_score > 0 else 0,
                "moyen": round(len(moyen) / total_avec_score * 100, 1) if total_avec_score > 0 else 0,
                "bon": round(len(bon) / total_avec_score * 100, 1) if total_avec_score > 0 else 0
            },
            "biens_critiques_faible": len(biens_critiques_faible),
            "details_faible": details_faible,
            "seuils": {
                "critique": SEUIL_SCORE_CRITIQUE,
                "moyen": SEUIL_SCORE_MOYEN,
                "bon": SEUIL_SCORE_BON
            },
            "couleurs": {
                "critique": Couleurs.SCORE_CRITIQUE,
                "moyen": Couleurs.SCORE_MOYEN,
                "bon": Couleurs.SCORE_BON
            }
        }

    # ============================================================
    # J. ÉVOLUTION DU PATRIMOINE
    # ============================================================

    def get_rapport_evolution_patrimoine(self, annee_debut: int, annee_fin: int) -> dict:
        """
        Génère un rapport d'évolution du patrimoine sur plusieurs années
        """
        evolution = []
        
        for annee in range(annee_debut, annee_fin + 1):
            debut_annee = datetime(annee, 1, 1)
            fin_annee = datetime(annee, 12, 31)
            
            biens = self.db.query(Bien).filter(
                Bien.date_acquisition <= fin_annee,
                (Bien.date_sortie.is_(None) | (Bien.date_sortie >= debut_annee))
            ).all()
            
            acquisitions = self.db.query(Bien).filter(
                Bien.date_acquisition >= debut_annee,
                Bien.date_acquisition <= fin_annee
            ).all()
            
            sorties = self.db.query(Bien).filter(
                Bien.date_sortie >= debut_annee,
                Bien.date_sortie <= fin_annee
            ).all()
            
            valeur_totale = sum(float(b.prix_acquisition or 0) for b in biens)
            valeur_acquisitions = sum(float(b.prix_acquisition or 0) for b in acquisitions)
            valeur_sorties = sum(float(b.prix_acquisition or 0) for b in sorties)
            
            total_amort = self.db.query(func.sum(Amortissement.annuite_comptable)).filter(
                Amortissement.exercice == annee
            ).scalar() or 0
            
            vnc_totale = sum(
                float(b.prix_acquisition or 0) - float(b.cumul_amortissement or 0)
                for b in biens
            )
            
            evolution.append({
                "annee": annee,
                "nombre_biens": len(biens),
                "valeur_totale_brute": self._round_value(valeur_totale),
                "valeur_acquisitions": self._round_value(valeur_acquisitions),
                "valeur_sorties": self._round_value(valeur_sorties),
                "total_amortissements": self._round_value(total_amort),
                "vnc_totale": self._round_value(vnc_totale),
                "taux_amortissement": round(total_amort / valeur_totale * 100, 2) if valeur_totale > 0 else 0
            })
        
        return {
            "annee_debut": annee_debut,
            "annee_fin": annee_fin,
            "evolution": evolution,
            "tendance": self._calculer_tendance_evolution(evolution)
        }

    def _calculer_tendance_evolution(self, evolution: list) -> dict:
        """Calcule la tendance d'évolution du patrimoine"""
        if len(evolution) < 2:
            return {"message": "Données insuffisantes pour calculer la tendance"}
        
        premiere = evolution[0]
        derniere = evolution[-1]
        
        variation_brute = derniere["valeur_totale_brute"] - premiere["valeur_totale_brute"]
        variation_pourcent = (variation_brute / premiere["valeur_totale_brute"] * 100) if premiere["valeur_totale_brute"] > 0 else 0
        
        return {
            "variation_valeur_brute": self._round_value(variation_brute),
            "variation_pourcent": self._round_value(variation_pourcent),
            "tendance": "HAUSSE" if variation_brute > 0 else "BAISSE" if variation_brute < 0 else "STABLE",
            "evolution_biens": derniere["nombre_biens"] - premiere["nombre_biens"]
        }

    # ============================================================
    # K. RAPPORT MAINTENANCES PRÉVENTIVES AUTO-GÉNÉRÉES
    # ============================================================

    def get_rapport_maintenances_preventives(self) -> dict:
        """
        Génère un rapport sur les maintenances préventives auto-générées
        """
        maintenances_auto = self.db.query(Maintenance).filter(
            Maintenance.origine == TypeOrigineMaintenance.AUTO
        ).all()
        
        planifiees = [m for m in maintenances_auto if m.statut == StatutMaintenance.PLANIFIEE]
        en_cours = [m for m in maintenances_auto if m.statut == StatutMaintenance.EN_COURS]
        terminees = [m for m in maintenances_auto if m.statut == StatutMaintenance.TERMINEE]
        
        scores_depart = [m.score_fiabilite_depart for m in maintenances_auto if m.score_fiabilite_depart is not None]
        score_moyen_depart = sum(scores_depart) / len(scores_depart) if scores_depart else 0
        
        details = [
            {
                "id_maintenance": m.id_maintenance,
                "id_bien": m.id_bien,
                "date_planifiee": m.date_planifiee.strftime("%d/%m/%Y") if m.date_planifiee else "",
                "statut": m.statut.value if m.statut else "",
                "score_fiabilite_depart": self._round_value(m.score_fiabilite_depart),
                "cout": self._round_value(m.cout),
                "description": m.description
            }
            for m in maintenances_auto
            if m.statut != StatutMaintenance.TERMINEE
        ]
        
        return {
            "total_auto_generes": len(maintenances_auto),
            "planifiees": len(planifiees),
            "en_cours": len(en_cours),
            "terminees": len(terminees),
            "score_moyen_depart": self._round_value(score_moyen_depart),
            "details_en_cours": details[:10],
            "taux_realisation": round(len(terminees) / len(maintenances_auto) * 100, 1) if maintenances_auto else 0
        }

    # ============================================================
    # L. PROJECTIONS – UTILISATION DES DONNÉES PRÉ-CALCULÉES
    # ============================================================

    def get_projections_pre_calculees(self, bien_id: int) -> List[ProjectionInvestissement]:
        """
        Retourne les projections pré-calculées par le CRON pour un bien.
        Lecture rapide, pas de calcul.
        """
        return self.db.query(ProjectionInvestissement).filter(
            ProjectionInvestissement.bien_id == bien_id
        ).order_by(ProjectionInvestissement.annee_projection).all()

    def get_projections_synthese(self, bien_id: int) -> dict:
        """
        Retourne une synthèse des projections pré-calculées.
        """
        projections = self.get_projections_pre_calculees(bien_id)

        if not projections:
            bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
            return {
                "bien_id": bien_id,
                "bien_designation": self._get_bien_designation(bien) if bien else f"Bien #{bien_id}",
                "total_projections": 0,
                "projections": [],
                "message": "Aucune projection disponible. Veuillez exécuter le CRON de projections."
            }

        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        
        return {
            "bien_id": bien_id,
            "bien_designation": self._get_bien_designation(bien) if bien else f"Bien #{bien_id}",
            "total_projections": len(projections),
            "projections": [
                {
                    "annee": p.annee_projection,
                    "score_fiabilite_projete": float(p.score_fiabilite_projete or 0),
                    "vnc_projetee": float(p.vnc_projetee or 0),
                    "cout_remplacement": float(p.cout_remplacement_estime or 0),
                    "critere_fin_amortissement": p.critere_fin_amortissement,
                    "critere_score_fiabilite": p.critere_score_fiabilite,
                    "statut": p.statut.value if p.statut else None
                }
                for p in projections
            ]
        }

    def get_projections_pluriannuelles(self) -> dict:
        """
        Retourne les projections pluriannuelles agrégées pour tous les biens.
        Utilise les données pré-calculées par le CRON.
        """
        annee_actuelle = datetime.now().year

        projections = self.db.query(ProjectionInvestissement).filter(
            ProjectionInvestissement.annee_projection >= annee_actuelle + 1
        ).all()

        if not projections:
            return {
                "annee_base": annee_actuelle,
                "total_projections": 0,
                "projections_par_annee": [],
                "total_5_ans": 0,
                "message": "Aucune projection disponible. Veuillez exécuter le CRON de projections."
            }

        projections_par_annee = {}
        for proj in projections:
            annee = proj.annee_projection
            if annee not in projections_par_annee:
                projections_par_annee[annee] = []
            projections_par_annee[annee].append(proj)

        resultat = {
            "annee_base": annee_actuelle,
            "total_projections": len(projections),
            "projections_par_annee": [],
            "total_5_ans": 0,
            "biens_a_remplacer": []
        }

        for annee in sorted(projections_par_annee.keys()):
            projs = projections_par_annee[annee]
            budget_requis = sum(float(p.cout_remplacement_estime or 0) for p in projs)
            nb_biens = len(projs)
            
            resultat["total_5_ans"] += budget_requis
            resultat["projections_par_annee"].append({
                "annee": annee,
                "budget_requis": self._round_value(budget_requis),
                "nb_biens": nb_biens,
                "details": [
                    {
                        "bien_id": p.bien_id,
                        "bien_designation": self._get_bien_designation_from_id(p.bien_id),
                        "cout_remplacement": float(p.cout_remplacement_estime or 0),
                        "critere": self._get_critere_projection(p)
                    }
                    for p in projs
                ]
            })

        resultat["total_5_ans"] = self._round_value(resultat["total_5_ans"])
        resultat["biens_a_remplacer"] = self._get_biens_a_remplacer(projections, annee_actuelle)

        return resultat

    def _get_biens_a_remplacer(self, projections: List[ProjectionInvestissement], annee_actuelle: int) -> List[dict]:
        """
        Identifie les biens à remplacer dans les 2 ans.
        """
        biens_a_remplacer = []
        biens_vus = set()

        for proj in projections:
            if proj.annee_projection <= annee_actuelle + 2:
                if proj.critere_fin_amortissement or proj.critere_score_fiabilite:
                    if proj.bien_id not in biens_vus:
                        biens_vus.add(proj.bien_id)
                        bien = self.db.query(Bien).filter(Bien.id_bien == proj.bien_id).first()
                        biens_a_remplacer.append({
                            "bien_id": proj.bien_id,
                            "designation": self._get_bien_designation(bien) if bien else f"Bien #{proj.bien_id}",
                            "annee": proj.annee_projection,
                            "cout_remplacement": float(proj.cout_remplacement_estime or 0),
                            "raison": "Amortissement complet" if proj.critere_fin_amortissement else "Score de fiabilité critique"
                        })

        return biens_a_remplacer

    # ============================================================
    # M. MÉTHODE GÉNÉRER_PROJECTION_PLURIANNUELLE – DÉPRÉCIÉE
    # ============================================================

    def generer_projection_pluriannuelle(self, *args, **kwargs) -> dict:
        """
        🔴 DÉPRÉCIÉ — Les projections sont générées par le CRON.

        Utiliser get_projections_pre_calculees() pour les projections d'un bien,
        ou get_projections_pluriannuelles() pour une vue agrégée.
        """
        raise RuntimeError(
            "Méthode dépréciée. Les projections sont générées par cron_projections. "
            "Utiliser get_projections_pre_calculees() pour les projections d'un bien, "
            "ou get_projections_pluriannuelles() pour une vue agrégée."
        )