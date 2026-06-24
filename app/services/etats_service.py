# backend/app/services/etats_service.py
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import joinedload

from ..models.bien import Bien, EtatBien
from ..models.composant import Composant
from ..models.maintenance import Maintenance, StatutMaintenance, TypeMaintenance
from ..models.panne import Panne, StatutPanne, TypePanne
from ..models.besoin import Besoin
from ..models.ligne_besoin import LigneBesoin
from ..models.validation import Validation
from ..models.utilisateur import Utilisateur


class EtatsService:
    """Service dédié à la récupération des données pour les états imprimables (PDF)"""

    def __init__(self, db: Session):
        self.db = db

    def _calculer_age_bien(self, date_acquisition) -> int:
        if not date_acquisition:
            return 0
        today = datetime.now().date()
        return today.year - date_acquisition.year

    def _get_valeur_attr(self, bien: Bien, *attrs) -> str:
        """Récupère la première valeur non None d'une liste d'attributs"""
        for attr in attrs:
            value = getattr(bien, attr, None)
            if value is not None:
                return value
        return ""

    def _get_marque_fabricant(self, bien: Bien) -> str:
        """Récupère la marque ou le fabricant selon le type de bien"""
        if bien.type_bien == "vehicule":
            return getattr(bien, 'marque', '') or ''
        elif bien.type_bien == "machine":
            return getattr(bien, 'fabricant', '') or ''
        elif bien.type_bien == "ordinateur":
            return getattr(bien, 'marque', '') or ''
        return ''

    def _get_modele(self, bien: Bien) -> str:
        """Récupère le modèle selon le type de bien"""
        return getattr(bien, 'modele', '') or ''

    def _get_numero_serie(self, bien: Bien) -> str:
        """Récupère le numéro de série ou immatriculation selon le type de bien"""
        if bien.type_bien == "vehicule":
            return getattr(bien, 'immatriculation', '') or ''
        else:
            return getattr(bien, 'numero_serie', '') or ''

    def get_fiche_bien_data(self, bien_id: int) -> Optional[Dict[str, Any]]:
        """Récupère toutes les données nécessaires pour la fiche d'un bien"""
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            return None

        # Composants
        composants = self.db.query(Composant).filter(
            Composant.id_bien == bien_id
        ).all()

        # Maintenances récentes (5 dernières)
        maintenances = self.db.query(Maintenance).filter(
            Maintenance.id_bien == bien_id
        ).order_by(Maintenance.date_planifiee.desc()).limit(5).all()

        # Pannes récentes (5 dernières)
        pannes = self.db.query(Panne).filter(
            Panne.id_bien == bien_id
        ).order_by(Panne.date_declaration.desc()).limit(5).all()

        # Valeurs
        valeur_composants = sum(float(c.valeur) for c in composants) if composants else 0
        prix_acquisition = float(bien.prix_acquisition) if bien.prix_acquisition else 0
        valeur_structure = prix_acquisition - valeur_composants

        # Construction du dictionnaire de sortie
        return {
            "bien": {
                "id_bien": bien.id_bien,
                "qr_code": bien.qr_code,
                "type_bien": bien.type_bien,
                "etat": bien.etat.value if bien.etat else "INCONNU",
                "marque_fabricant": self._get_marque_fabricant(bien),
                "modele": self._get_modele(bien),
                "numero_serie": self._get_numero_serie(bien),
                "date_acquisition": bien.date_acquisition.strftime("%d/%m/%Y") if bien.date_acquisition else "",
                "prix_acquisition": prix_acquisition,
                "localisation": bien.localisation or "",
                "description": bien.description or "",
                "age_ans": self._calculer_age_bien(bien.date_acquisition),
                "specificites": self._get_specificites_bien(bien)
            },
            "composants": [
                {
                    "designation": c.designation,
                    "valeur": float(c.valeur),
                    "duree_vie_ans": c.duree_vie_ans,
                    "date_remplacement": c.date_remplacement.strftime("%d/%m/%Y") if c.date_remplacement else None
                }
                for c in composants
            ],
            "valeur_composants": valeur_composants,
            "valeur_structure": valeur_structure,
            "maintenances_recentes": [
                {
                    "date": m.date_planifiee.strftime("%d/%m/%Y") if m.date_planifiee else "",
                    "type": m.type_maintenance.value if m.type_maintenance else "",
                    "cout": float(m.cout) if m.cout else 0
                }
                for m in maintenances
            ],
            "pannes_recentes": [
                {
                    "date": p.date_declaration.strftime("%d/%m/%Y") if p.date_declaration else "",
                    "type": p.type_panne.value if p.type_panne else "",
                    "statut": p.statut.value if p.statut else ""
                }
                for p in pannes
            ],
            "date_generation": datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
        }

    def _get_specificites_bien(self, bien: Bien) -> Dict[str, Any]:
        """Retourne un dictionnaire des champs spécifiques selon le type de bien"""
        specifics = {}
        
        if bien.type_bien == "vehicule":
            specifics = {
                "type_vehicule": getattr(bien, 'type_vehicule', None),
                "immatriculation": getattr(bien, 'immatriculation', None),
                "consommation_carburant": getattr(bien, 'consommation_carburant', None),
                "poids": getattr(bien, 'poids', None),
                "dimension": getattr(bien, 'dimension', None),
                "type_propulsion": getattr(bien, 'type_propulsion', None)
            }
        elif bien.type_bien == "machine":
            specifics = {
                "fabricant": getattr(bien, 'fabricant', None),
                "numero_serie": getattr(bien, 'numero_serie', None),
                "puissance": getattr(bien, 'puissance', None),
                "type_alimentation": getattr(bien, 'type_alimentation', None),
                "tension_normal": getattr(bien, 'tension_normal', None),
                "service_affecte": getattr(bien, 'service_affecte', None),
                "responsable": getattr(bien, 'responsable', None),
                "consommation_elec": getattr(bien, 'consommation_elec', None),
                "frequence_maintenance": getattr(bien, 'frequence_maintenance', None)
            }
        elif bien.type_bien == "ordinateur":
            specifics = {
                "marque": getattr(bien, 'marque', None),
                "modele": getattr(bien, 'modele', None),
                "processeur": getattr(bien, 'processeur', None),
                "ram": getattr(bien, 'ram', None),
                "stockage": getattr(bien, 'stockage', None),
                "adresse_ip": getattr(bien, 'adresse_ip', None),
                "utilisateur_affecte": getattr(bien, 'utilisateur_affecte', None)
            }
        
        # Filtrer les valeurs None
        return {k: v for k, v in specifics.items() if v is not None}

    def get_fiche_amortissement_data(self, bien_id: int) -> Optional[Dict[str, Any]]:
        """Récupère toutes les données pour la fiche d'amortissement d'un bien"""
        from ..models.amortissement import Amortissement
        from ..models.regles_amortissement import RegleAmortissement
        from ..models.ecriture_comptable import EcritureComptable
        
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            return None
        
        # Récupérer l'amortissement en cours
        amortissement = self.db.query(Amortissement).filter(
            Amortissement.id_bien == bien_id,
            Amortissement.statut == "EN_COURS"
        ).first()
        
        if not amortissement:
            # Si aucun amortissement en cours, en créer un virtuel pour l'affichage
            amortissement = self._creer_amortissement_virtuel(bien)
        
        # Récupérer les règles d'amortissement
        regle = self.db.query(RegleAmortissement).filter(
            RegleAmortissement.categorie_bien == bien.type_bien
        ).first()
        
        # Calcul du plan d'amortissement
        plan_amortissement = self._calculer_plan_amortissement(
            bien, amortissement, regle
        )
        
        # Récupérer les écritures comptables liées
        ecritures = self.db.query(EcritureComptable).filter(
            EcritureComptable.id_bien == bien_id
        ).order_by(EcritureComptable.date_ecriture.desc()).limit(10).all()
        
        # Calcul des statistiques avec les bons attributs
        cumul_amorti = amortissement.cumul_comptable if hasattr(amortissement, 'cumul_comptable') else 0
        valeur_origine = amortissement.valeur_origine if hasattr(amortissement, 'valeur_origine') else float(bien.prix_acquisition or 0)
        vnc_actuelle = amortissement.valeur_nette_comptable if hasattr(amortissement, 'valeur_nette_comptable') else valeur_origine
        
        return {
            "bien": {
                "id_bien": bien.id_bien,
                "qr_code": bien.qr_code,
                "type_bien": bien.type_bien,
                "marque_fabricant": self._get_marque_fabricant(bien),
                "modele": self._get_modele(bien),
                "date_acquisition": bien.date_acquisition.strftime("%d/%m/%Y") if bien.date_acquisition else "",
                "prix_acquisition": float(bien.prix_acquisition) if bien.prix_acquisition else 0,
                "localisation": bien.localisation or "",
                "etat": bien.etat.value if bien.etat else "INCONNU"
            },
            "amortissement": {
                "methode": amortissement.methode.value if hasattr(amortissement, 'methode') and amortissement.methode else "LINEAIRE",
                "exercice_en_cours": amortissement.exercice if hasattr(amortissement, 'exercice') else datetime.now().year,
                "taux_comptable": float(amortissement.taux_comptable) if hasattr(amortissement, 'taux_comptable') and amortissement.taux_comptable else 20.0,
                "taux_fiscal": float(amortissement.taux_fiscal) if hasattr(amortissement, 'taux_fiscal') and amortissement.taux_fiscal else 25.0,
                "duree_vie_comptable_ans": amortissement.duree_vie_comptable_ans if hasattr(amortissement, 'duree_vie_comptable_ans') else 5,
                "duree_vie_fiscale_ans": amortissement.duree_vie_fiscale_ans if hasattr(amortissement, 'duree_vie_fiscale_ans') else 4,
                "valeur_origine": valeur_origine,
                "valeur_residuelle": float(amortissement.valeur_residuelle) if hasattr(amortissement, 'valeur_residuelle') and amortissement.valeur_residuelle else 0,
                "cumul_amorti": cumul_amorti,
                "vnc_actuelle": vnc_actuelle,
                "date_debut": amortissement.date_debut.strftime("%d/%m/%Y") if hasattr(amortissement, 'date_debut') and amortissement.date_debut else "",
                "statut": amortissement.statut.value if hasattr(amortissement, 'statut') and amortissement.statut else "EN_COURS"
            },
            "plan_amortissement": plan_amortissement,
            "ecritures_comptables": [
                {
                    "date": e.date_ecriture.strftime("%d/%m/%Y") if e.date_ecriture else "",
                    "type": e.type_operation.value if hasattr(e, 'type_operation') and e.type_operation else "",
                    "compte_debit": e.compte_debit if hasattr(e, 'compte_debit') else "",
                    "compte_credit": e.compte_credit if hasattr(e, 'compte_credit') else "",
                    "montant": float(e.montant) if hasattr(e, 'montant') else 0,
                    "validee": e.validee if hasattr(e, 'validee') else False
                }
                for e in ecritures
            ],
            "statistiques": self._calculer_statistiques_amortissement(amortissement, plan_amortissement),
            "date_generation": datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
        }

    def _creer_amortissement_virtuel(self, bien: Bien):
        """Crée un objet amortissement virtuel pour l'affichage"""
        from ..models.amortissement import MethodeAmortissement, StatutAmortissement
        
        class AmortissementVirtuel:
            pass
        
        virtuel = AmortissementVirtuel()
        virtuel.methode = MethodeAmortissement.LINEAIRE
        virtuel.exercice = datetime.now().year
        virtuel.taux_comptable = 20.0
        virtuel.taux_fiscal = 25.0
        virtuel.duree_vie_comptable_ans = 5
        virtuel.duree_vie_fiscale_ans = 4
        virtuel.valeur_origine = float(bien.prix_acquisition) if bien.prix_acquisition else 0
        virtuel.valeur_residuelle = 0
        virtuel.cumul_comptable = 0  # ← Correction: cumul_comptable
        virtuel.valeur_nette_comptable = virtuel.valeur_origine
        virtuel.date_debut = bien.date_acquisition
        virtuel.statut = StatutAmortissement.EN_COURS
        
        return virtuel

    def _calculer_plan_amortissement(self, bien: Bien, amortissement, regle) -> List[Dict[str, Any]]:
        """Calcule le plan d'amortissement sur la durée de vie du bien"""
        plan = []
        
        valeur_origine = amortissement.valeur_origine
        valeur_residuelle = amortissement.valeur_residuelle
        base_amortissable = valeur_origine - valeur_residuelle
        
        # CORRECTION: Vérifier si date_debut existe
        if hasattr(amortissement, 'date_debut') and amortissement.date_debut:
            annee_debut = amortissement.date_debut.year
        else:
            annee_debut = datetime.now().year
        
        duree = amortissement.duree_vie_comptable_ans
        
        # CORRECTION: Utiliser cumul_comptable au lieu de cumul_amorti
        cumul = amortissement.cumul_comptable if hasattr(amortissement, 'cumul_comptable') else 0
        vnc_debut = amortissement.valeur_nette_comptable if hasattr(amortissement, 'valeur_nette_comptable') else valeur_origine
        
        for i in range(duree):
            annee = annee_debut + i
            # Calcul de l'annuité de l'année
            if i == duree - 1:
                # Dernière année : amortir le reste
                annuite = vnc_debut
            else:
                annuite = base_amortissable / duree
            
            # Ajustement pour la première année si acquisition en cours d'année
            if i == 0 and bien.date_acquisition:
                mois_restants = 12 - (bien.date_acquisition.month)
                if mois_restants < 12 and mois_restants > 0:
                    annuite = (annuite * mois_restants) / 12
            
            cumul += annuite
            vnc_fin = max(0, valeur_origine - cumul)
            
            plan.append({
                "annee": annee,
                "vnc_debut": round(vnc_debut, 0),
                "annuite": round(annuite, 0),
                "cumul": round(cumul, 0),
                "vnc_fin": round(vnc_fin, 0),
                "est_annee_courante": annee == datetime.now().year
            })
            
            vnc_debut = vnc_fin
        
        return plan

    def _calculer_statistiques_amortissement(self, amortissement, plan: List[Dict]) -> Dict[str, Any]:
        """Calcule les statistiques de l'amortissement"""
        if not plan:
            return {}
        
        duree_totale = len(plan)
        annee_courante = None
        for p in plan:
            if p.get("est_annee_courante"):
                annee_courante = p
                break
        
        # CORRECTION: Utiliser cumul_comptable au lieu de cumul_amorti
        cumul_amorti = amortissement.cumul_comptable if hasattr(amortissement, 'cumul_comptable') else 0
        valeur_origine = amortissement.valeur_origine if hasattr(amortissement, 'valeur_origine') else 0
        
        pourcentage_amorti = 0
        if valeur_origine > 0:
            pourcentage_amorti = (cumul_amorti / valeur_origine) * 100
        
        annees_restantes = duree_totale - (annee_courante["annee"] - plan[0]["annee"] + 1) if annee_courante else 0
        
        return {
            "duree_totale_ans": duree_totale,
            "pourcentage_amorti": round(pourcentage_amorti, 1),
            "annees_restantes": max(0, annees_restantes),
            "annuite_moyenne": round(valeur_origine / duree_totale, 0) if duree_totale > 0 else 0
        }

    def _format_nom_utilisateur(self, user: Optional[Utilisateur]) -> str:
        if not user:
            return "N/A"
        return f"{user.prenom or ''} {user.nom or ''}".strip() or "N/A"

    def _bien_designation(self, bien: Bien) -> str:
        label = (
            f"{getattr(bien, 'marque', None) or getattr(bien, 'fabricant', None) or ''} "
            f"{getattr(bien, 'modele', '')}"
        ).strip()
        return label or f"Bien #{bien.id_bien}"

    def _statut_besoin_label(self, statut) -> str:
        labels = {
            "BROUILLON": "Brouillon",
            "EN_VALIDATION": "En validation",
            "DG_VALIDE": "Validé DG",
            "COMPTABLE_VALIDE": "Validé Comptable",
            "CAISSE_VALIDE": "Validé Caisse",
            "APPROUVEE": "Approuvée",
            "REJETE": "Rejetée",
            "ATTENTE_STOCK": "En attente de stock",
        }
        value = statut.value if hasattr(statut, "value") else str(statut)
        return labels.get(value, value)

    def get_etat_besoin_data(self, besoin_id: int) -> Optional[Dict[str, Any]]:
        """Données pour l'état de sortie imprimable d'une demande de besoin."""
        besoin = (
            self.db.query(Besoin)
            .options(
                joinedload(Besoin.lignes).joinedload(LigneBesoin.piece),
                joinedload(Besoin.validations).joinedload(Validation.validateur),
                joinedload(Besoin.panne).joinedload(Panne.bien),
                joinedload(Besoin.panne).joinedload(Panne.technicien),
            )
            .filter(Besoin.id_besoin == besoin_id)
            .first()
        )
        if not besoin:
            return None

        panne = besoin.panne
        bien = panne.bien if panne else None
        technicien = panne.technicien if panne else None

        lignes = []
        for ligne in besoin.lignes or []:
            piece = ligne.piece
            reference = piece.numero_serie if piece and piece.numero_serie else f"PCE-{ligne.id_piece}"
            stock_actuel = piece.stock_actuel if piece else 0
            lignes.append({
                "reference": reference,
                "designation": piece.designation if piece else "N/A",
                "quantite": ligne.quantite,
                "prix_unitaire": float(ligne.prix_unitaire or 0),
                "prix_total": float(ligne.prix_total or 0),
                "stock_actuel": stock_actuel,
            })

        validations_par_ordre = {v.ordre_validateur.value: v for v in (besoin.validations or [])}
        circuit_validation = []
        for ordre in ["DG", "COMPTABLE", "CAISSE"]:
            validation = validations_par_ordre.get(ordre)
            circuit_validation.append({
                "ordre": ordre,
                "libelle": {
                    "DG": "Directeur Général",
                    "COMPTABLE": "Service Comptable",
                    "CAISSE": "Service Caisse",
                }.get(ordre, ordre),
                "validateur": self._format_nom_utilisateur(validation.validateur) if validation else None,
                "decision": validation.decision.value if validation and validation.decision else "EN_ATTENTE",
                "date": validation.date_validation.strftime("%d/%m/%Y") if validation and validation.date_validation else None,
                "commentaire": validation.commentaire if validation else None,
            })

        return {
            "besoin": {
                "id_besoin": besoin.id_besoin,
                "numero_demande": besoin.numero_demande,
                "date_creation": besoin.date_creation.strftime("%d/%m/%Y") if besoin.date_creation else "",
                "statut": self._statut_besoin_label(besoin.statut),
                "montant_total": float(besoin.montant_total or 0),
                "observations": besoin.observations or "",
            },
            "panne": {
                "id_panne": panne.id_panne if panne else None,
                "type_panne": panne.type_panne.value if panne and panne.type_panne else "",
                "statut": panne.statut.value if panne and panne.statut else "",
                "description": (panne.description or "")[:200] if panne else "",
            } if panne else None,
            "bien": {
                "id_bien": bien.id_bien,
                "qr_code": bien.qr_code or "",
                "designation": self._bien_designation(bien),
                "type_bien": bien.type_bien or "",
                "localisation": bien.localisation or "",
            } if bien else None,
            "technicien": self._format_nom_utilisateur(technicien),
            "lignes": lignes,
            "circuit_validation": circuit_validation,
            "date_generation": datetime.now().strftime("%d/%m/%Y à %H:%M:%S"),
        }