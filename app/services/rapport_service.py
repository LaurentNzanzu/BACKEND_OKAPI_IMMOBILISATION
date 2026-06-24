# backend/app/services/rapport_service.py
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract, or_
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date
from decimal import Decimal

from ..models.bien import Bien, EtatBien, StatutComptable
from ..models.panne import Panne, StatutPanne, TypePanne
from ..models.maintenance import Maintenance, StatutMaintenance, TypeMaintenance
from ..models.amortissement import Amortissement, MethodeAmortissement
from ..models.ecriture_comptable import EcritureComptable, TypeOperationEnum, StatutEcriture
from ..models.mouvement_bien import MouvementBien, TypeMouvementEnum
from ..models.composant import Composant
from ..models.plan_comptable import PlanComptable
from ..models.fournisseur import Fournisseur
from ..models.cession import Cession


class RapportService:
    def __init__(self, db: Session):
        self.db = db

    def _date_to_datetime(self, d: date) -> datetime:
        """Convertit une date en datetime avec heure 00:00:00"""
        if isinstance(d, datetime):
            return d
        return datetime.combine(d, datetime.min.time())

    def _format_currency(self, value) -> str:
        """Formatte un montant en FCFA"""
        if value is None:
            return "0,00 FCFA"
        return f"{float(value):,.2f} FCFA"

    def _round_value(self, value) -> float:
        """Arrondit une valeur à 2 décimales"""
        if value is None:
            return 0.0
        return round(float(value), 2)

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
            Bien.localisation,
            func.sum(Panne.cout_total_reparation).label('cout_pannes'),
            func.sum(Maintenance.cout).label('cout_maintenances')
        ).outerjoin(Panne, Panne.id_bien == Bien.id_bien).outerjoin(
            Maintenance, Maintenance.id_bien == Bien.id_bien
        ).filter(
            or_(
                Panne.date_declaration.between(date_debut, date_fin),
                Maintenance.date_debut_reelle.between(date_debut, date_fin)
            )
        ).group_by(Bien.id_bien).order_by(
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
            Bien.localisation,
            Bien.prix_acquisition,
            Bien.cumul_amortissement
        ).join(Bien, Cession.id_bien == Bien.id_bien).filter(
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
            Bien.localisation
        ).join(Bien, MouvementBien.id_bien == Bien.id_bien).filter(
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
            Bien.localisation,
            Bien.prix_acquisition,
            Bien.cumul_amortissement,
            Bien.date_sortie
        ).filter(
            Bien.statut_comptable == "MIS_AU_REBUT",  # String, pas Enum
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
            Bien.localisation,
            Bien.date_acquisition
        ).join(Bien, Amortissement.id_bien == Bien.id_bien).filter(
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
        # On récupère les données des cessions
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
        # Pour l'instant, on met des valeurs par défaut
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