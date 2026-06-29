from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal
from datetime import datetime
from typing import Dict, List

from ..models.bien import Bien, EtatBien
from ..models.panne import Panne
from ..models.maintenance import Maintenance
from ..models.piece_rechange import PieceRechange
from ..models.amortissement import Amortissement


class EtatService:
    """Service de génération des états financiers et de gestion."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_fiche_stock(self) -> Dict:
        """
        Génère la fiche de stock.
        """
        pieces = self.db.query(PieceRechange).all()
        
        total_pieces = sum(p.stock_actuel for p in pieces) if pieces else 0
        valeur_totale = sum(p.stock_actuel * (p.prix_achat or 0) for p in pieces) if pieces else 0
        
        alertes = [
            {
                "designation": p.designation,
                "stock_actuel": p.stock_actuel,
                "stock_minimum": p.stock_minimum,
                "manquant": p.stock_minimum - p.stock_actuel
            }
            for p in pieces if p.stock_actuel is not None and p.stock_minimum is not None and p.stock_actuel < p.stock_minimum
        ]
        
        categories = {}
        for p in pieces:
            cat = p.compatible_avec or "AUTRE"
            if cat not in categories:
                categories[cat] = {"quantite": 0, "valeur": 0}
            categories[cat]["quantite"] += (p.stock_actuel or 0)
            categories[cat]["valeur"] += (p.stock_actuel or 0) * (p.prix_achat or 0)
        
        return {
            "total_pieces": total_pieces,
            "valeur_totale": float(valeur_totale),
            "pieces_par_categorie": [
                {"categorie": k, **v} for k, v in categories.items()
            ],
            "alertes_reapprovisionnement": alertes,
            "mouvements_recents": []
        }
    
    def get_etat_parc(self) -> Dict:
        """
        Génère l'état du parc (santé des biens).
        """
        biens = self.db.query(Bien).all()
        
        repartition = {}
        for etat in EtatBien:
            repartition[etat.value] = sum(1 for b in biens if b.etat == etat)
        
        biens_critiques = [
            {
                "id": b.id_bien,
                "designation": b.description or f"Bien #{b.id_bien}",
                "score": float(b.score_fiabilite) if b.score_fiabilite is not None else None,
                "etat": b.etat.value if hasattr(b.etat, 'value') else str(b.etat)
            }
            for b in biens if getattr(b, 'est_critique', False)
        ]
        
        scores = [float(b.score_fiabilite) for b in biens if b.score_fiabilite is not None]
        score_moyen = sum(scores) / len(scores) if scores else 0.0
        
        seuil_critique = 0.20
        seuil_standard = 0.05
        
        biens_a_remplacer = []
        for b in biens:
            vnc_ratio = getattr(b, 'ratio_vnc_restante', 0) or 0
            seuil = seuil_critique if getattr(b, 'est_critique', False) else seuil_standard
            if vnc_ratio <= seuil:
                biens_a_remplacer.append({
                    "id": b.id_bien,
                    "designation": b.description or f"Bien #{b.id_bien}",
                    "vnc_ratio": round(float(vnc_ratio), 4),
                    "est_critique": getattr(b, 'est_critique', False)
                })
        
        return {
            "total_biens": len(biens),
            "repartition_etat": repartition,
            "biens_critiques": biens_critiques,
            "score_moyen": round(score_moyen, 2),
            "biens_a_remplacer": biens_a_remplacer
        }
    
    def get_etat_financier(self, exercice: int = None) -> Dict:
        """
        Génère l'état financier.
        """
        if not exercice:
            exercice = datetime.utcnow().year
        
        biens = self.db.query(Bien).all()
        valeur_patrimoine = sum(float(b.prix_acquisition or 0) for b in biens)
        cumul_amortissements = sum(float(b.cumul_amortissement or 0) for b in biens)
        vnc_totale = valeur_patrimoine - cumul_amortissements
        
        maintenances = self.db.query(Maintenance).filter(
            func.extract('year', Maintenance.date_debut) == exercice
        ).all()
        depenses_maintenance = sum(float(m.cout or 0) for m in maintenances)
        
        pannes = self.db.query(Panne).filter(
            func.extract('year', Panne.date_declaration) == exercice
        ).all()
        cout_pannes = sum(float(p.cout_total_reparation or 0) for p in pannes)
        
        return {
            "exercice": exercice,
            "valeur_patrimoine": round(valeur_patrimoine, 2),
            "cumul_amortissements": round(cumul_amortissements, 2),
            "vnc_totale": round(vnc_totale, 2),
            "depenses_maintenance": round(depenses_maintenance, 2),
            "cout_pannes": round(cout_pannes, 2)
        }
    
    def get_etat_sortie(self, exercice: int = None) -> Dict:
        """
        Génère l'état de sortie (dépenses par maintenance).
        """
        if not exercice:
            exercice = datetime.utcnow().year
        
        maintenances = self.db.query(Maintenance).filter(
            func.extract('year', Maintenance.date_debut) == exercice
        ).all()
        
        par_type = {}
        for m in maintenances:
            type_maint = m.type_maintenance.value if hasattr(m.type_maintenance, 'value') else str(m.type_maintenance)
            if type_maint not in par_type:
                par_type[type_maint] = 0.0
            par_type[type_maint] += float(m.cout or 0)
        
        evolution = []
        for mois in range(1, 13):
            mois_m = [m for m in maintenances if m.date_debut and m.date_debut.month == mois]
            total_mois = sum(float(m.cout or 0) for m in mois_m)
            evolution.append({
                "mois": mois,
                "montant": round(total_mois, 2)
            })
        
        return {
            "exercice": exercice,
            "total_depenses": round(sum(par_type.values()), 2),
            "par_type": {k: round(v, 2) for k, v in par_type.items()},
            "evolution_mensuelle": evolution
        }
