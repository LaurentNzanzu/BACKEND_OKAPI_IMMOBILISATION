import logging
from ..models.role import Role
from ..models.utilisateur import Utilisateur
from ..services.notification_service import NotificationService
from ..models.notification import TypeNotificationEnum
from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import unicodedata
import re
import sqlalchemy as sa

from ..models.decision_ia import DecisionIA, TypeDecisionEnum
from ..models.bien import Bien
from ..models.amortissement import Amortissement
from ..models.maintenance import Maintenance
from ..models.panne import Panne
from ..models.piece_rechange import PieceRechange
from ..models.ligne_besoin import LigneBesoin
from ..models.besoin import Besoin, StatutBesoin
from ..core.config import settings

logger = logging.getLogger(__name__)

PRIX_NEUF_FACTOR = getattr(settings, 'PRIX_NEUF_FACTOR', 1.20)
MAINTENANCE_ESTIMEE_PCT = getattr(settings, 'MAINTENANCE_ESTIMEE_PCT', 0.10)
SEUIL_REMPLACEMENT = getattr(settings, 'SEUIL_REMPLACEMENT', 0.85)

class IADecisionService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    def _round(self, value: float) -> float:
        return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def _get_designation_bien(self, bien: Bien) -> str:
        marque = getattr(bien, 'marque', None) or getattr(bien, 'fabricant', None) or ''
        modele = getattr(bien, 'modele', None) or ''
        designation = f"{marque} {modele}".strip()
        if not designation:
            designation = f"Bien #{bien.id_bien}"
        return designation

    def calculer_health_score(self, bien_id: int, current_user_id: Optional[int] = None) -> Dict[str, Any]:
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError("Bien non trouvé")

        amort = self.db.query(Amortissement).filter(
            Amortissement.id_bien == bien_id
        ).order_by(Amortissement.exercice.desc()).first()

        valeur_origine = float(bien.prix_acquisition) if bien.prix_acquisition else 0.0
        duree_vie = float(amort.duree_vie_comptable_ans) if amort and amort.duree_vie_comptable_ans else 5.0

        if duree_vie <= 0:
            duree_vie = 5.0
        if valeur_origine <= 0:
            valeur_origine = 1.0

        one_year_ago = datetime.utcnow() - timedelta(days=365)
        maints = self.db.query(Maintenance).filter(
            Maintenance.id_bien == bien_id,
            Maintenance.date_fin_reelle >= one_year_ago
        ).all()
        cout_maintenance_12m = sum(float(m.cout) for m in maints if m.cout)

        pannes = self.db.query(Panne).filter(
            Panne.id_bien == bien_id,
            Panne.date_declaration >= one_year_ago
        ).count()

        date_acq = bien.date_acquisition or datetime.utcnow().date()
        age_actuel = (datetime.utcnow().date() - date_acq).days / 365.25

        vnc_actuelle = valeur_origine - (valeur_origine / duree_vie * min(age_actuel, duree_vie))
        if vnc_actuelle < 0:
            vnc_actuelle = 0.0

        amort_annuel_base = valeur_origine / duree_vie if duree_vie > 0 else 0

        ratio_vnc = min(1.0, max(0.0, vnc_actuelle / valeur_origine))
        composante_financiere = ratio_vnc * 0.30

        ratio_maintenance = min(1.0, cout_maintenance_12m / valeur_origine)
        composante_maintenance = (1 - ratio_maintenance) * 0.30

        ratio_pannes = min(1.0, pannes / 10.0)
        composante_fiabilite = (1 - ratio_pannes) * 0.20

        ratio_age_restant = min(1.0, max(0.0, (duree_vie - age_actuel) / duree_vie))
        composante_duree_vie = ratio_age_restant * 0.20

        score_brut = composante_financiere + composante_maintenance + composante_fiabilite + composante_duree_vie
        score_final = round(score_brut * 100, 2)

        if score_final >= 90:
            statut = "EXCELLENT"
            recommandation = "Aucune action requise"
        elif score_final >= 70:
            statut = "SURVEILLE"
            recommandation = "Maintenance préventive recommandée"
        elif score_final >= 50:
            statut = "CRITIQUE"
            recommandation = "Intervention nécessaire dans les 6 mois"
        else:
            statut = "URGENT"
            recommandation = "Remplacement à prévoir immédiatement"

        response_data = {
            "bien_id": bien_id,
            "bien_designation": self._get_designation_bien(bien),
            "score": score_final,
            "statut": statut,
            "valeur_origine": round(valeur_origine, 2),
            "duree_vie_totale": round(duree_vie, 2),
            "cout_maintenance_12m": round(cout_maintenance_12m, 2),
            "frequence_pannes_12m": pannes,
            "age_actuel_ans": round(age_actuel, 2),
            "vnc": round(vnc_actuelle, 2),
            "amortissement_annuel_base": round(amort_annuel_base, 2),
            "recommandation": recommandation,
            "date_analyse": datetime.utcnow().isoformat()
        }

        # 🆕 NOTIFICATION: Health Score critique
        if current_user_id and score_final < 70:
            try:
                # Envoyer aux DG et COMPTABLE
                destinataires = self.db.query(Utilisateur).join(Role).filter(
                    Role.nom.in_(["DG", "COMPTABLE"])
                ).all()
                
                if score_final < 50:
                    titre = f"🚨 Alerte critique - {bien_id}"
                    contenu = f"Health Score: {score_final}/100. Remplacement immédiat recommandé."
                else:
                    titre = f"⚠️ Bien critique - {bien_id}"
                    contenu = f"Health Score: {score_final}/100. Intervention dans les 6 mois."
                
                self.notification_service.envoyer_notification(
                    ids_destinataires=[d.id for d in destinataires],
                    type_notif=TypeNotificationEnum.DECISION_IA_HEALTH_SCORE,
                    titre=titre,
                    contenu=contenu,
                    lien=f"/ia/aide-decision?bien_id={bien_id}",
                )
            except Exception as e:
                logger.error(f"Erreur notification Health Score: {e}")


        if current_user_id:
            try:
                decision_record = DecisionIA(
                    id_bien=bien_id,
                    id_utilisateur=current_user_id,
                    type_decision=TypeDecisionEnum.HEALTH_SCORE,
                    score=score_final,
                    statut=statut,
                    contenu=str(response_data),
                    source_modele="health_score_rule_based_v1",
                    date_creation=datetime.utcnow()
                )
                self.db.add(decision_record)
                self.db.commit()
                logger.info(f"Decision IA enregistrée pour bien ID: {bien_id}")
            except Exception as e:
                logger.error(f"Erreur lors de l'enregistrement de la décision IA pour bien {bien_id}: {e}")
                self.db.rollback()

        return response_data

    def generer_recommandations_parc(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        tous_les_biens = self.db.query(Bien).all()
        resultats = []

        for bien in tous_les_biens:
            try:
                health_data = self.calculer_health_score(bien.id_bien, user_id)
                resultats.append(health_data)
            except Exception as e:
                logger.warning(f"Erreur calcul health score pour bien {bien.id_bien}: {e}")
                continue

        resultats.sort(key=lambda x: x.get('score', 100))

        return resultats

    def _get_moyenne_pannes_flotte(self, type_bien: str) -> float:
        one_year_ago = datetime.utcnow() - timedelta(days=365)

        subquery = self.db.query(
            Panne.id_bien,
            sa.func.count(Panne.id_panne).label('nb_pannes')
        ).filter(
            Panne.date_declaration >= one_year_ago
        ).group_by(Panne.id_bien).subquery()

        avg_result = self.db.query(
            sa.func.avg(subquery.c.nb_pannes)
        ).join(Bien, Bien.id_bien == subquery.c.id_bien).filter(
            Bien.type_bien == type_bien
        ).scalar()

        return float(avg_result) if avg_result else 0.0

    def generer_decision_strategique(self, bien_id: int, id_utilisateur: int) -> Dict[str, Any]:
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError("Bien non trouvé")

        metrics = self.calculer_health_score(bien_id, id_utilisateur)

        valeur_origine = metrics["valeur_origine"]
        duree_vie = metrics["duree_vie_totale"]
        cout_maint_12m = metrics["cout_maintenance_12m"]
        freq_pannes = metrics["frequence_pannes_12m"]
        age_actuel = metrics["age_actuel_ans"]
        vnc_actuelle = metrics["vnc"]
        amort_annuel_base = metrics["amortissement_annuel_base"]

        cout_conserver_annuel = self._round(amort_annuel_base + cout_maint_12m)

        prix_neuf_estime = valeur_origine * PRIX_NEUF_FACTOR
        amortissement_estime = prix_neuf_estime / duree_vie if duree_vie > 0 else 0
        maintenance_estimee = prix_neuf_estime * MAINTENANCE_ESTIMEE_PCT
        cout_remplacer_annuel = self._round(amortissement_estime + maintenance_estimee)

        economie_annuelle = self._round(cout_conserver_annuel - cout_remplacer_annuel)

        seuil_decision = cout_conserver_annuel * SEUIL_REMPLACEMENT

        if cout_remplacer_annuel < seuil_decision:
            decision = "REMPLACEMENT_RECOMMANDE"
            delai = "6_mois"
        else:
            decision = "CONSERVATION"
            delai = "N/A"

        raisons = []

        if valeur_origine > 0:
            ratio_entretien = cout_maint_12m / valeur_origine
            if ratio_entretien > 0.15:
                raisons.append(f"Ratio coût entretien / valeur = {int(ratio_entretien*100)}% (seuil max recommandé 15%)")

        if bien.type_bien:
            moyenne_flotte = self._get_moyenne_pannes_flotte(bien.type_bien)
            if moyenne_flotte > 0 and freq_pannes > moyenne_flotte:
                raisons.append(f"Fréquence pannes: {freq_pannes}x (moyenne flotte: {self._round(moyenne_flotte)}x)")

        if valeur_origine > 0 and (vnc_actuelle / valeur_origine) < 0.20:
            raisons.append(f"VNC actuelle: {int(vnc_actuelle)} FCFA (moins de 20% de la valeur d'origine)")

        if age_actuel > (duree_vie * 0.7):
            raisons.append(f"Âge avancé: {int(age_actuel)} ans (durée de vie: {int(duree_vie)} ans)")

        if economie_annuelle > 0:
            raisons.append(f"Le coût de remplacement est inférieur au coût de conservation ({int(economie_annuelle)} FCFA/an)")

        if not raisons:
            raisons.append("Analyse basée sur les données disponibles : stabilité opérationnelle")

        actions_suggerees = []
        if decision == "REMPLACEMENT_RECOMMANDE":
            budget_previs = self._round(prix_neuf_estime)
            actions_suggerees = [
                "Programmer la cession via le module Mouvements",
                f"Commencer la recherche d'un bien neuf (budget prévisionnel: {int(budget_previs)} FCFA)",
                "Prévoir le remplacement dans les 6 mois"
            ]
        else:
            actions_suggerees = [
                "Planifier une maintenance préventive approfondie",
                "Surveiller l'évolution des coûts de maintenance",
                "Revoir l'analyse dans 6 mois"
            ]

        contenu_json = {
            "bien_id": bien_id,
            "decision": decision,
            "delai": delai,
            "cout_conserver_annuel": cout_conserver_annuel,
            "cout_remplacer_annuel": cout_remplacer_annuel,
            "economie_annuelle": economie_annuelle,
            "raisons": raisons,
            "actions_suggerees": actions_suggerees
        }

        try:
            decision_ia = DecisionIA(
                id_bien=bien_id,
                id_utilisateur=id_utilisateur,
                type_decision=TypeDecisionEnum.DECISION_STRATEGIQUE,
                score=None,
                statut=decision,
                contenu=str(contenu_json),
                source_modele="decision_strategique_rule_based_v1"
            )
            self.db.add(decision_ia)
            self.db.commit()
        except Exception as e:
            logger.error(f"Erreur enregistrement décision stratégique: {e}")
            self.db.rollback()

        return {
            "bien_id": bien_id,
            "bien_designation": self._get_designation_bien(bien),
            "decision": decision,
            "delai": delai,
            "cout_conserver_annuel": cout_conserver_annuel,
            "cout_remplacer_annuel": cout_remplacer_annuel,
            "economie_annuelle": economie_annuelle,
            "raisons": raisons,
            "actions_suggerees": actions_suggerees,
            "date_analyse": datetime.utcnow()
        }

    def generer_alertes_achat_pieces(self, id_utilisateur: Optional[int] = None) -> List[Dict[str, Any]]:
        pieces = self.db.query(PieceRechange).filter(PieceRechange.est_active == True).all()
        
        one_year_ago = datetime.utcnow() - timedelta(days=365)
        
        consommation = self.db.query(
            LigneBesoin.id_piece,
            sa.func.sum(LigneBesoin.quantite).label('total_sorties')
        ).join(
            Besoin, LigneBesoin.id_besoin == Besoin.id_besoin
        ).filter(
            Besoin.statut == StatutBesoin.APPROUVEE,
            Besoin.date_creation >= one_year_ago
        ).group_by(
            LigneBesoin.id_piece
        ).all()
        
        consommation_dict = {row.id_piece: row.total_sorties for row in consommation}
        
        alertes = []
        decisions_a_enregistrer = []
        
        for piece in pieces:
            stock_actuel = piece.stock_actuel or 0
            stock_minimum = piece.stock_minimum or 5
            total_sorties = consommation_dict.get(piece.id_piece, 0)
            consommation_mensuelle = total_sorties / 12 if total_sorties > 0 else 0
            
            stock_projete_60j = stock_actuel - (consommation_mensuelle * 2)
            
            # ✅ NOUVELLE CONDITION : Alerte basée sur stock actuel < stock minimum
            if stock_actuel < stock_minimum:
                action = "ACHAT_URGENT"
                quantite_recommandee = stock_minimum - stock_actuel
            elif stock_projete_60j < 0:
                action = "ACHAT_URGENT"
                quantite_recommandee = int(abs(stock_projete_60j) + stock_minimum)
            elif stock_projete_60j < stock_minimum:
                action = "SURVEILLER"
                quantite_recommandee = max(0, stock_minimum - stock_actuel)
            else:
                action = "OK"
                quantite_recommandee = 0
            
            if action != "OK":
                alerte = {
                    "piece_id": piece.id_piece,
                    "numero_serie": piece.numero_serie,
                    "designation": piece.designation,
                    "stock_actuel": stock_actuel,
                    "stock_minimum": stock_minimum,
                    "consommation_mensuelle_moyenne": round(consommation_mensuelle, 2),
                    "stock_estime_60j": round(stock_projete_60j, 2),
                    "action": action,
                    "quantite_recommandee": quantite_recommandee,
                    "date_analyse": datetime.utcnow().isoformat()
                }
                alertes.append(alerte)
                
                if id_utilisateur:
                    decisions_a_enregistrer.append(
                        DecisionIA(
                            id_piece=piece.id_piece,
                            id_utilisateur=id_utilisateur,
                            type_decision=TypeDecisionEnum.ACHAT_RECOMMANDE,
                            score=None,
                            statut=action,
                            contenu=str(alerte),
                            source_modele="alerte_achat_rule_based_v1",
                        )
                    )

        if id_utilisateur and decisions_a_enregistrer:
            try:
                self.db.add_all(decisions_a_enregistrer)
                self.db.commit()
            except Exception as e:
                logger.error(f"Erreur enregistrement alertes d'achat: {e}")
                self.db.rollback()
        
        alertes.sort(key=lambda x: 0 if x["action"] == "ACHAT_URGENT" else 1)
        
        return alertes
    def _normaliser_question(self, question: str) -> str:
        texte = question.lower()
        texte = unicodedata.normalize('NFD', texte)
        texte = ''.join(c for c in texte if unicodedata.category(c) != 'Mn')
        texte = re.sub(r'[^\w\s]', ' ', texte)
        mots_vides = {'le', 'la', 'les', 'un', 'une', 'des', 'de', 'du', 'et', 'ou', 'donc', 'or', 'ni', 'car', 'a', 'en', 'sur', 'dans', 'par', 'pour', 'avec', 'sans', 'sous', 'contre', 'vers', 'chez', 'hors', 'jusqu', 'loin', 'pres', 'cote', 'face', 'devant', 'derriere', 'entre', 'autour'}
        mots = texte.split()
        mots_filtres = [m for m in mots if m not in mots_vides]
        return ' '.join(mots_filtres)

    def _detecter_intention(self, question_norm: str) -> Optional[str]:
        intentions = {
            "biens_critiques": {
                "mots_cles": ["remplacer", "remplacement", "equipement", "critique", "urgent", "changer", "renouveler", "panne", "arret", "hs"]
            },
            "biens_a_surveiller": {
                "mots_cles": ["surveiller", "attention", "prevenir", "anticiper", "fragile", "etat", "sante"]
            },
            "amortis_total": {
                "mots_cles": ["amorti", "amortissement", "totalement", "plus de valeur", "vnc nulle", "fin de vie", "usure", "fin de course"]
            },
            "maintenance_couteuse": {
                "mots_cles": ["maintenance", "entretien", "cout", "cher", "couteux", "depense", "reparation", "facture", "chere"]
            },
            "pannes_frequentes": {
                "mots_cles": ["panne", "pannes", "frequent", "souvent", "tombe", "casse", "degradation", "defaillance", "probleme", "en panne"]
            },
            "alertes_pieces": {
                "mots_cles": ["piece", "stock", "commander", "achat", "fournisseur", "rupture", "manque", "achat urgent", "commande"]
            },
            "sante_parc": {
                "mots_cles": ["sante", "etat", "global", "vue d'ensemble", "synthese", "resume", "parc", "ensemble", "bilan"]
            },
            "valeur_parc": {
                "mots_cles": ["valeur", "prix", "cout total", "investissement", "patrimoine", "totalite", "somme"]
            }
        }

        for intent, data in intentions.items():
            for mot in data["mots_cles"]:
                if mot in question_norm:
                    return intent
        return None

    def _executer_requete(self, intention: str) -> tuple[str, List[Dict[str, Any]]]:
        if intention == "biens_critiques":
            biens = self.db.query(Bien).all()
            biens_critiques = []
            for b in biens:
                try:
                    score_data = self.calculer_health_score(b.id_bien)
                    if score_data["score"] < 50:
                        biens_critiques.append({
                            "bien_id": b.id_bien,
                            "designation": self._get_designation_bien(b),
                            "score": score_data["score"],
                            "statut": score_data["statut"]
                        })
                except ValueError:
                    continue
            texte = self._formater_liste_biens(biens_critiques, "sont critiques")
            return texte, biens_critiques

        elif intention == "biens_a_surveiller":
            biens = self.db.query(Bien).all()
            biens_surveilles = []
            for b in biens:
                try:
                    score_data = self.calculer_health_score(b.id_bien)
                    if 50 <= score_data["score"] < 70:
                        biens_surveilles.append({
                            "bien_id": b.id_bien,
                            "designation": self._get_designation_bien(b),
                            "score": score_data["score"],
                            "statut": score_data["statut"]
                        })
                except ValueError:
                    continue
            texte = self._formater_liste_biens(biens_surveilles, "sont a surveiller")
            return texte, biens_surveilles

        elif intention == "amortis_total":
            biens = self.db.query(Bien, Amortissement).join(Amortissement, Bien.id_bien == Amortissement.id_bien).filter(
                (Amortissement.valeur_nette_comptable / Amortissement.valeur_origine) < 0.10
            ).all()
            biens_amortis = []
            for b, a in biens:
                biens_amortis.append({
                    "bien_id": b.id_bien,
                    "designation": self._get_designation_bien(b),
                    "valeur_nette_comptable": a.valeur_nette_comptable,
                    "valeur_origine": a.valeur_origine
                })
            texte = self._formater_liste_biens([{"designation": b["designation"]} for b in biens_amortis], "sont totalement amortis")
            return texte, biens_amortis

        elif intention == "maintenance_couteuse":
            one_year_ago = datetime.utcnow() - timedelta(days=365)
            maints = self.db.query(
                Maintenance.id_bien,
                sa.func.sum(Maintenance.cout).label('cout_total')
            ).filter(
                Maintenance.date_fin_reelle >= one_year_ago
            ).group_by(Maintenance.id_bien).subquery()

            biens = self.db.query(Bien, Amortissement, maints.c.cout_total).join(
                Amortissement, Bien.id_bien == Amortissement.id_bien
            ).join(
                maints, Bien.id_bien == maints.c.id_bien
            ).filter(
                maints.c.cout_total > (Amortissement.valeur_origine * 0.20)
            ).all()

            biens_chers = []
            for b, a, cout in biens:
                biens_chers.append({
                    "bien_id": b.id_bien,
                    "designation": self._get_designation_bien(b),
                    "cout_maintenance_12m": float(cout),
                    "valeur_origine": a.valeur_origine
                })
            texte = self._formater_liste_biens([{"designation": b["designation"]} for b in biens_chers], "ont un cout de maintenance eleve")
            return texte, biens_chers

        elif intention == "pannes_frequentes":
            one_year_ago = datetime.utcnow() - timedelta(days=365)
            pannes = self.db.query(
                Panne.id_bien,
                sa.func.count(Panne.id_panne).label('nb_pannes')
            ).filter(
                Panne.date_declaration >= one_year_ago
            ).group_by(Panne.id_bien).having(sa.func.count(Panne.id_panne) > 3).subquery()

            biens = self.db.query(Bien, pannes.c.nb_pannes).join(
                pannes, Bien.id_bien == pannes.c.id_bien
            ).all()

            biens_freq = []
            for b, nb in biens:
                biens_freq.append({
                    "bien_id": b.id_bien,
                    "designation": self._get_designation_bien(b),
                    "nb_pannes": nb
                })
            texte = self._formater_liste_biens([{"designation": b["designation"], "nb_pannes": b["nb_pannes"]} for b in biens_freq], "ont des pannes frequentes")
            return texte, biens_freq

        elif intention == "alertes_pieces":
            alertes = self.generer_alertes_achat_pieces()
            alertes_filtrees = [a for a in alertes if a["action"] in ["ACHAT_URGENT", "SURVEILLER"]]
            if alertes_filtrees:
                pieces_liste = ", ".join([f"{a['designation']}" for a in alertes_filtrees])
                texte = f"{len(alertes_filtrees)} piece(s) doivent etre commandees : {pieces_liste}."
            else:
                texte = "Aucune piece n'a besoin d'etre commandee pour le moment."
            return texte, alertes_filtrees

        elif intention == "sante_parc":
            biens = self.db.query(Bien).all()
            total = len(biens)
            excellents = 0
            surveilles = 0
            critiques = 0
            urgents = 0
            for b in biens:
                try:
                    score_data = self.calculer_health_score(b.id_bien)
                    if score_data["score"] >= 90:
                        excellents += 1
                    elif 70 <= score_data["score"] < 90:
                        surveilles += 1
                    elif 50 <= score_data["score"] < 70:
                        critiques += 1
                    else:
                        urgents += 1
                except ValueError:
                    continue
            texte = f"Le parc compte {total} biens : {excellents} excellents, {surveilles} a surveiller, {critiques} critiques, {urgents} urgents."
            return texte, [{"total": total, "excellents": excellents, "surveilles": surveilles, "critiques": critiques, "urgents": urgents}]

        elif intention == "valeur_parc":
            total_value = self.db.query(sa.func.sum(Bien.prix_acquisition)).scalar()
            if total_value:
                texte = f"La valeur totale du parc est de {total_value:,.0f} FCFA."
                return texte, [{"valeur_totale": total_value}]
            else:
                texte = "Impossible de calculer la valeur totale du parc."
                return texte, []

        return "Aucune donnee disponible pour cette requete.", []

    def _formater_liste_biens(self, biens: List[Dict], suffixe: str) -> str:
        if len(biens) == 0:
            return f"Aucun bien {suffixe}."
        elif len(biens) == 1:
            b = biens[0]
            nom = b.get("designation", "Inconnu")
            score = b.get("score", "")
            nb_pannes = b.get("nb_pannes", "")
            if score:
                return f"1 bien {suffixe} : {nom} (score {score})"
            elif nb_pannes:
                return f"1 bien {suffixe} : {nom} ({nb_pannes} pannes)"
            else:
                return f"1 bien {suffixe} : {nom}"
        else:
            noms = []
            for b in biens:
                nom = b.get("designation", "Inconnu")
                score = b.get("score", "")
                nb_pannes = b.get("nb_pannes", "")
                if score:
                    noms.append(f"{nom} (score {score})")
                elif nb_pannes:
                    noms.append(f"{nom} ({nb_pannes} pannes)")
                else:
                    noms.append(f"{nom}")
            return f"{len(biens)} biens {suffixe} : " + ", ".join(noms)

    def assister_conversationnel(self, question: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        question_norm = self._normaliser_question(question)
        intention = self._detecter_intention(question_norm)

        if not intention:
            texte_aide = (
                "Je n'ai pas compris votre question. Voici ce que je peux faire :\n"
                "- Quels biens doivent etre remplaces ?\n"
                "- Quels biens sont totalement amortis ?\n"
                "- Quelles sont les pieces a commander ?\n"
                "- Quelle est la sante du parc ?\n"
                "- Quels sont les biens avec des pannes frequentes ?\n"
                "- Quels biens coutent cher en maintenance ?\n"
                "- Quels biens sont a surveiller ?"
            )
            return {"reponse": texte_aide, "donnees": []}

        texte_reponse, donnees_brutes = self._executer_requete(intention)
        return {"reponse": texte_reponse, "donnees": donnees_brutes}