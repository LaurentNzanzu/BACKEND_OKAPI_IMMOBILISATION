# backend/app/services/maintenance_service.py
from asyncio.log import logger
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone

from ..models.maintenance import Maintenance, TypeMaintenance, StatutMaintenance, TypeOrigineMaintenance
from ..models.bien import Bien, EtatBien
from ..models.panne import Panne, StatutPanne
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..models.alerte_vnc import AlerteVNC, StatutAlerteVNC
from ..models.journal_evenements_immobilisation import JournalEvenementImmobilisation, TypeEvenementImmobilisation
from ..models.projection_investissement import ProjectionInvestissement, StatutProjection
from ..schemas.maintenance import MaintenanceCreate, MaintenanceUpdate
from ..services.notification_service import NotificationService
from ..models.notification import TypeNotificationEnum
from ..services.bien_service import BienService
from ..core.constants import (
    SEUIL_SCORE_CRITIQUE,
    SEUIL_SCORE_MOYEN,
    SEUIL_VNC_CRITIQUE,
    SEUIL_VNC_STANDARD,
    FACTEUR_FREQUENCE_PANNES,
    POIDS_COUT_REPARATION,
    DELAI_PLANIFICATION_AUTO,
    ANNEE_PROJECTION_DEBUT,
    ANNEE_PROJECTION_FIN,
    TAUX_OBSOLESCENCE_DEFAUT
)


class MaintenanceService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
        self.bien_service = BienService(db)

    # ============================================================
    # MÉTHODES DE GESTION DES MAINTENANCES (AVEC TRANSACTIONS ACID)
    # ============================================================

    def planifier_maintenance(self, data: MaintenanceCreate, id_technicien: int) -> Maintenance:
        """
        Planifie une nouvelle maintenance.
        
        ✅ TRANSACTION ACID avec with db.begin()
        """
        try:
            with self.db.begin():
                bien = self.db.query(Bien).filter(
                    Bien.id_bien == data.id_bien
                ).with_for_update().first()

                if not bien:
                    raise ValueError(f"Bien {data.id_bien} non trouvé")

                now = datetime.now(timezone.utc)
                date_planifiee = data.date_planifiee
                if date_planifiee.tzinfo is None:
                    date_planifiee = date_planifiee.replace(tzinfo=timezone.utc)

                if date_planifiee < now:
                    raise ValueError("La date planifiée ne peut pas être dans le passé")

                maintenance = Maintenance(
                    id_bien=data.id_bien,
                    id_technicien=id_technicien,
                    type_maintenance=data.type_maintenance,
                    date_planifiee=data.date_planifiee,
                    description=data.description,
                    periodicite_jours=data.periodicite_jours,
                    observation=data.observation,
                    statut=StatutMaintenance.PLANIFIEE,
                    origine=TypeOrigineMaintenance.MANUEL
                )
                self.db.add(maintenance)

                # Le commit est automatique à la sortie du with

        except SQLAlchemyError as e:
            logger.error(f"Erreur planification maintenance: {e}")
            raise ValueError(f"Échec de la planification: {str(e)}")

        self.db.refresh(maintenance)

        # Journaliser l'événement (hors transaction pour ne pas bloquer)
        try:
            self._journaliser_evenement(
                bien_id=data.id_bien,
                type_evenement=TypeEvenementImmobilisation.MAINTENANCE,
                libelle=f"Maintenance {data.type_maintenance.value} planifiée le {data.date_planifiee.strftime('%d/%m/%Y')}",
                utilisateur_id=id_technicien
            )
        except Exception as e:
            logger.warning(f"Erreur journalisation (non bloquante): {e}")

        # Notification
        self._notifier_techniciens(maintenance, bien)

        return maintenance

    def _notifier_techniciens(self, maintenance: Maintenance, bien: Bien):
        """Envoie une notification aux techniciens."""
        try:
            techniciens = self.db.query(Utilisateur).join(Role).filter(Role.nom == "TECHNICIEN").all()
            if techniciens:
                designation = getattr(bien, 'marque', '') or getattr(bien, 'fabricant', '') or ''
                self.notification_service.envoyer_notification(
                    ids_destinataires=[t.id for t in techniciens],
                    type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                    titre=f"🔧 Nouvelle maintenance planifiée - {designation}",
                    contenu=f"Une maintenance {maintenance.type_maintenance.value} est planifiée le {maintenance.date_planifiee.strftime('%d/%m/%Y')} pour le bien {designation} {getattr(bien, 'modele', '')}",
                    lien=f"/maintenances/{maintenance.id_maintenance}"
                )
        except Exception as e:
            logger.error(f"Erreur envoi notification maintenance: {e}")

    def get_maintenances_by_bien(self, id_bien: int, skip: int = 0, limit: int = 100) -> List[Maintenance]:
        """Récupère les maintenances d'un bien."""
        return self.db.query(Maintenance).filter(
            Maintenance.id_bien == id_bien
        ).order_by(Maintenance.date_planifiee.desc()).offset(skip).limit(limit).all()

    def get_maintenances_by_panne(self, id_panne: int) -> List[Maintenance]:
        """Récupère les maintenances d'une panne."""
        return (
            self.db.query(Maintenance)
            .filter(Maintenance.id_panne == id_panne)
            .order_by(Maintenance.date_creation.desc())
            .all()
        )

    def get_maintenances_by_technicien(self, id_technicien: int, statut: Optional[str] = None) -> List[Maintenance]:
        """Récupère les maintenances assignées à un technicien."""
        query = self.db.query(Maintenance).filter(Maintenance.id_technicien == id_technicien)
        if statut:
            query = query.filter(Maintenance.statut == statut)
        return query.order_by(Maintenance.date_planifiee.asc()).all()

    def get_maintenances_a_venir(self, jours: int = 7) -> List[Maintenance]:
        """Récupère les maintenances planifiées dans les X jours."""
        now = datetime.now(timezone.utc)
        date_limite = now + timedelta(days=jours)
        return self.db.query(Maintenance).filter(
            Maintenance.statut == StatutMaintenance.PLANIFIEE,
            Maintenance.date_planifiee <= date_limite,
            Maintenance.date_planifiee >= now
        ).order_by(Maintenance.date_planifiee.asc()).all()

    def get_maintenances_en_retard(self) -> List[Maintenance]:
        """Récupère les maintenances planifiées non réalisées et en retard."""
        now = datetime.now(timezone.utc)
        return self.db.query(Maintenance).filter(
            Maintenance.statut == StatutMaintenance.PLANIFIEE,
            Maintenance.date_planifiee < now
        ).order_by(Maintenance.date_planifiee.asc()).all()

    def get_maintenance(self, id_maintenance: int) -> Optional[Maintenance]:
        """Récupère une maintenance par son ID."""
        return self.db.query(Maintenance).filter(Maintenance.id_maintenance == id_maintenance).first()

    def update_maintenance(self, id_maintenance: int, data: MaintenanceUpdate) -> Optional[Maintenance]:
        """
        Met à jour une maintenance.
        
        ✅ TRANSACTION ACID avec with db.begin()
        """
        try:
            with self.db.begin():
                maintenance = self.db.query(Maintenance).filter(
                    Maintenance.id_maintenance == id_maintenance
                ).with_for_update().first()

                if not maintenance:
                    return None

                update_data = data.model_dump(exclude_unset=True)
                for field, value in update_data.items():
                    setattr(maintenance, field, value)

        except SQLAlchemyError as e:
            logger.error(f"Erreur mise à jour maintenance {id_maintenance}: {e}")
            raise ValueError(f"Échec de la mise à jour: {str(e)}")

        self.db.refresh(maintenance)
        return maintenance

    def demarrer_maintenance(self, id_maintenance: int) -> Optional[Maintenance]:
        """
        Démarre une intervention.
        
        ✅ TRANSACTION ACID avec with db.begin()
        """
        try:
            with self.db.begin():
                maintenance = self.db.query(Maintenance).filter(
                    Maintenance.id_maintenance == id_maintenance
                ).with_for_update().first()

                if not maintenance:
                    return None

                if maintenance.statut != StatutMaintenance.PLANIFIEE:
                    raise ValueError(f"Impossible de démarrer une maintenance en statut {maintenance.statut.value}")

                maintenance.demarrer()

        except SQLAlchemyError as e:
            logger.error(f"Erreur démarrage maintenance {id_maintenance}: {e}")
            raise ValueError(f"Échec du démarrage: {str(e)}")

        self.db.refresh(maintenance)
        return maintenance

    def terminer_maintenance(
        self,
        id_maintenance: int,
        rapport: str,
        cout: float,
        pieces_remplacees: str = None
    ) -> Optional[Maintenance]:
        """
        Termine une intervention.
        
        ✅ TRANSACTION ACID avec with db.begin()
        """
        try:
            with self.db.begin():
                maintenance = self.db.query(Maintenance).filter(
                    Maintenance.id_maintenance == id_maintenance
                ).with_for_update().first()

                if not maintenance:
                    return None

                if maintenance.statut not in [StatutMaintenance.PLANIFIEE, StatutMaintenance.EN_COURS]:
                    raise ValueError(f"Impossible de terminer une maintenance en statut {maintenance.statut.value}")

                # Charger les relations
                self.db.refresh(maintenance, attribute_names=['panne', 'bien'])
                bien = maintenance.bien

                maintenance.terminer(rapport, cout)
                if pieces_remplacees:
                    maintenance.pieces_remplacees = pieces_remplacees

                # Mise à jour de l'état du bien
                self._mettre_a_jour_etat_bien_apres_maintenance(maintenance, bien)

        except SQLAlchemyError as e:
            logger.error(f"Erreur terminaison maintenance {id_maintenance}: {e}")
            raise ValueError(f"Échec de la terminaison: {str(e)}")

        self.db.refresh(maintenance)

        # Journaliser la fin de maintenance (hors transaction)
        try:
            self._journaliser_evenement(
                bien_id=maintenance.id_bien,
                type_evenement=TypeEvenementImmobilisation.MAINTENANCE,
                libelle=f"Maintenance {maintenance.type_maintenance.value} terminée - Coût: {cout} USD",
                montant=cout,
                utilisateur_id=maintenance.id_technicien
            )
        except Exception as e:
            logger.warning(f"Erreur journalisation (non bloquante): {e}")

        # Planifier la prochaine maintenance préventive
        if maintenance.type_maintenance == TypeMaintenance.PREVENTIVE and maintenance.periodicite_jours:
            self._planifier_prochaine_maintenance_preventive(maintenance)

        return maintenance

    def _mettre_a_jour_etat_bien_apres_maintenance(self, maintenance: Maintenance, bien: Optional[Bien]):
        """Met à jour l'état du bien après une maintenance."""
        if maintenance.type_maintenance == TypeMaintenance.CORRECTIVE and maintenance.id_panne:
            self.bien_service.changer_etat_bien(maintenance.id_bien, EtatBien.EN_TEST, commit=False)

            panne = maintenance.panne or self.db.query(Panne).filter(
                Panne.id_panne == maintenance.id_panne
            ).first()
            if panne:
                panne.changer_statut(StatutPanne.EN_TEST)

            # Notification au technicien
            self.notification_service.envoyer_notification(
                ids_destinataires=maintenance.id_technicien,
                type_notif=TypeNotificationEnum.BIEN_EN_TEST,
                titre="✅ Maintenance terminée - Phase de test",
                contenu=(
                    f"La maintenance corrective sur le bien est terminée. "
                    "Le bien est maintenant en phase de test."
                ),
                lien=f"/pannes/{maintenance.id_panne}",
            )
        else:
            nouvel_etat = EtatBien.BON
            if bien and bien.etat == EtatBien.USAGE:
                nouvel_etat = EtatBien.USAGE
            self.bien_service.changer_etat_bien(maintenance.id_bien, nouvel_etat, commit=False)

    def _planifier_prochaine_maintenance_preventive(self, maintenance: Maintenance):
        """Planifie automatiquement la prochaine maintenance préventive."""
        try:
            with self.db.begin():
                nouvelle_date = maintenance.date_fin_reelle + timedelta(days=maintenance.periodicite_jours)
                prochaine_maintenance = Maintenance(
                    id_bien=maintenance.id_bien,
                    id_technicien=maintenance.id_technicien,
                    type_maintenance=TypeMaintenance.PREVENTIVE,
                    date_planifiee=nouvelle_date,
                    description=f"Maintenance périodique - {maintenance.description}",
                    periodicite_jours=maintenance.periodicite_jours,
                    statut=StatutMaintenance.PLANIFIEE,
                    origine=TypeOrigineMaintenance.AUTO
                )
                self.db.add(prochaine_maintenance)
        except SQLAlchemyError as e:
            logger.error(f"Erreur planification prochaine maintenance: {e}")

    def reporter_maintenance(self, id_maintenance: int, nouvelle_date: datetime, motif: str = None) -> Optional[Maintenance]:
        """
        Reporte une maintenance à une date ultérieure.
        
        ✅ TRANSACTION ACID avec with db.begin()
        """
        try:
            with self.db.begin():
                maintenance = self.db.query(Maintenance).filter(
                    Maintenance.id_maintenance == id_maintenance
                ).with_for_update().first()

                if not maintenance:
                    return None

                if maintenance.statut not in [StatutMaintenance.PLANIFIEE]:
                    raise ValueError(f"Impossible de reporter une maintenance en statut {maintenance.statut.value}")

                now = datetime.now(timezone.utc)
                if nouvelle_date.tzinfo is None:
                    nouvelle_date = nouvelle_date.replace(tzinfo=timezone.utc)

                if nouvelle_date < now:
                    raise ValueError("La nouvelle date ne peut pas être dans le passé")

                maintenance.reporter(nouvelle_date, motif)

        except SQLAlchemyError as e:
            logger.error(f"Erreur report maintenance {id_maintenance}: {e}")
            raise ValueError(f"Échec du report: {str(e)}")

        self.db.refresh(maintenance)
        return maintenance

    def annuler_maintenance(self, id_maintenance: int) -> Optional[Maintenance]:
        """
        Annule une maintenance.
        
        ✅ TRANSACTION ACID avec with db.begin()
        """
        try:
            with self.db.begin():
                maintenance = self.db.query(Maintenance).filter(
                    Maintenance.id_maintenance == id_maintenance
                ).with_for_update().first()

                if not maintenance:
                    return None

                if maintenance.statut not in [StatutMaintenance.PLANIFIEE]:
                    raise ValueError(f"Impossible d'annuler une maintenance en statut {maintenance.statut.value}")

                maintenance.statut = StatutMaintenance.ANNULEE

        except SQLAlchemyError as e:
            logger.error(f"Erreur annulation maintenance {id_maintenance}: {e}")
            raise ValueError(f"Échec de l'annulation: {str(e)}")

        self.db.refresh(maintenance)
        return maintenance

    # ============================================================
    # STATISTIQUES (LECTURE SEULE)
    # ============================================================

    def get_statistiques(self, annee: int = None) -> dict:
        """Retourne les statistiques des maintenances."""
        query = self.db.query(Maintenance)
        if annee:
            query = query.filter(func.extract('year', Maintenance.date_creation) == annee)

        total = query.count()

        par_type = {}
        for t in TypeMaintenance:
            count = query.filter(Maintenance.type_maintenance == t).count()
            if count > 0:
                par_type[t.value] = count

        par_statut = {}
        for s in StatutMaintenance:
            count = query.filter(Maintenance.statut == s).count()
            if count > 0:
                par_statut[s.value] = count

        cout_total = query.filter(Maintenance.cout > 0).with_entities(func.sum(Maintenance.cout)).scalar() or 0
        cout_moyen = cout_total / total if total > 0 else 0

        terminees = query.filter(Maintenance.statut == StatutMaintenance.TERMINEE).count()
        taux_realisation = (terminees / total * 100) if total > 0 else 0

        alertes = self.get_maintenances_en_retard_count()

        return {
            "total_maintenances": total,
            "par_type": par_type,
            "par_statut": par_statut,
            "cout_total_annee": float(cout_total),
            "cout_moyen": float(cout_moyen),
            "taux_realisation": round(taux_realisation, 2),
            "alertes": alertes
        }

    def get_maintenances_en_retard_count(self) -> int:
        """Nombre de maintenances en retard."""
        now = datetime.now(timezone.utc)
        return self.db.query(Maintenance).filter(
            Maintenance.statut == StatutMaintenance.PLANIFIEE,
            Maintenance.date_planifiee < now
        ).count()

    def calculer_duree_vie_bien(self, id_bien: int) -> dict:
        """Calcule la durée de vie d'un bien basée sur ses maintenances."""
        bien = self.db.query(Bien).filter(Bien.id_bien == id_bien).first()
        if not bien:
            return None

        maintenances = self.get_maintenances_by_bien(id_bien)
        if not maintenances:
            return {
                "id_bien": id_bien,
                "date_acquisition": bien.date_acquisition,
                "age_ans": bien.calcul_age() if hasattr(bien, 'calcul_age') else 0,
                "derniere_maintenance": None,
                "prochaine_maintenance": None,
                "duree_vie_estimee": None
            }

        dernieres_terminees = [m for m in maintenances if m.statut == StatutMaintenance.TERMINEE]
        derniere_maintenance = max(dernieres_terminees, key=lambda m: m.date_fin_reelle) if dernieres_terminees else None

        prochaines = [m for m in maintenances if m.statut == StatutMaintenance.PLANIFIEE and m.date_planifiee >= datetime.now(timezone.utc)]
        prochaine_maintenance = min(prochaines, key=lambda m: m.date_planifiee) if prochaines else None

        return {
            "id_bien": id_bien,
            "designation": f"{getattr(bien, 'marque', '') or getattr(bien, 'fabricant', '')} {getattr(bien, 'modele', '')}".strip(),
            "date_acquisition": bien.date_acquisition,
            "age_ans": bien.calcul_age() if hasattr(bien, 'calcul_age') else 0,
            "derniere_maintenance": derniere_maintenance.date_fin_reelle if derniere_maintenance else None,
            "prochaine_maintenance": prochaine_maintenance.date_planifiee if prochaine_maintenance else None,
            "nombre_maintenances": len(maintenances),
            "cout_total_maintenances": sum(m.cout for m in maintenances),
            "duree_vie_estimee": bien.duree_vie_comptable_ans if hasattr(bien, 'duree_vie_comptable_ans') else 10
        }

    # ============================================================
    # SCORE DE FIABILITÉ (SYNCHRONE — UN SEUL BIEN)
    # ============================================================

    def calculer_score_fiabilite(self, bien_id: int) -> float:
        """
        Calcule le Score de Fiabilité (SF) pour un bien donné.
        Cette méthode est légère et peut être appelée synchronement.
        
        Formule: SF = 100 - (N × Facteur_Fréquence) - (CR/PA × 100)
        """
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien {bien_id} non trouvé")

        date_debut_exercice = bien.date_acquisition
        if date_debut_exercice:
            if date_debut_exercice.tzinfo is None:
                date_debut_exercice = datetime.combine(date_debut_exercice, datetime.min.time()).replace(tzinfo=timezone.utc)

        pannes = self.db.query(Panne).filter(
            Panne.id_bien == bien_id,
            Panne.date_declaration >= date_debut_exercice if date_debut_exercice else True,
            Panne.statut == StatutPanne.TERMINEE
        ).all()

        N = len(pannes)
        CR = sum(p.cout_reparation_total for p in pannes)
        PA = float(bien.prix_acquisition) if bien.prix_acquisition and bien.prix_acquisition > 0 else 1.0

        score = 100 - (N * FACTEUR_FREQUENCE_PANNES) - ((CR / PA) * 100)
        score = max(0.0, min(100.0, score))

        bien.score_fiabilite = score
        bien.date_dernier_calcul_score = datetime.now(timezone.utc)
        self.db.commit()

        self._journaliser_evenement(
            bien_id=bien_id,
            type_evenement=TypeEvenementImmobilisation.SCORE_FIABILITE,
            libelle=f"Score de fiabilité calculé: {score:.1f}% (N={N}, CR={CR:.2f}, PA={PA:.2f})",
            montant=score
        )

        return score

    def marquer_score_a_recalculer(self, bien_id: int) -> Bien:
        """
        Marque un bien comme nécessitant un recalcul de score.
        Appelé lors de la déclaration d'une panne.
        """
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien {bien_id} non trouvé")

        bien.score_a_recalculer = True
        self.db.commit()

        return bien

    def get_biens_a_recalculer(self, limite: int = 100) -> List[int]:
        """
        Retourne les IDs des biens marqués pour recalcul.
        Utilisé par la tâche CRON.
        """
        biens = self.db.query(Bien).filter(
            Bien.score_a_recalculer == True
        ).limit(limite).all()

        return [b.id_bien for b in biens]

    # ============================================================
    # ALERTES VNC ET MAINTENANCE AUTO (SYNCHRONES — UN SEUL BIEN)
    # ============================================================

    def verifier_et_planifier_maintenance_auto(self, bien_id: int) -> Optional[Maintenance]:
        """
        Vérifie si le bien nécessite une maintenance préventive auto
        et la planifie si nécessaire.
        """
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien {bien_id} non trouvé")

        if bien.score_fiabilite is None:
            self.calculer_score_fiabilite(bien_id)
            self.db.refresh(bien)

        if bien.est_critique and bien.score_fiabilite < SEUIL_SCORE_CRITIQUE:
            maintenance_existante = self.db.query(Maintenance).filter(
                Maintenance.id_bien == bien_id,
                Maintenance.statut == StatutMaintenance.PLANIFIEE,
                Maintenance.origine == TypeOrigineMaintenance.AUTO,
                Maintenance.date_creation >= datetime.now(timezone.utc) - timedelta(days=30)
            ).first()

            if not maintenance_existante:
                date_planifiee = datetime.now(timezone.utc) + timedelta(days=DELAI_PLANIFICATION_AUTO)

                try:
                    with self.db.begin():
                        nouvelle_maintenance = Maintenance(
                            id_bien=bien_id,
                            type_maintenance=TypeMaintenance.PREVENTIVE,
                            origine=TypeOrigineMaintenance.AUTO,
                            score_fiabilite_depart=bien.score_fiabilite,
                            date_planifiee=date_planifiee,
                            statut=StatutMaintenance.PLANIFIEE,
                            description=f"Maintenance préventive auto générée (Score: {bien.score_fiabilite:.1f}%)"
                        )
                        self.db.add(nouvelle_maintenance)

                except SQLAlchemyError as e:
                    logger.error(f"Erreur planification maintenance auto: {e}")
                    return None

                self.db.refresh(nouvelle_maintenance)

                self._journaliser_evenement(
                    bien_id=bien_id,
                    type_evenement=TypeEvenementImmobilisation.MAINTENANCE,
                    libelle=f"Maintenance préventive auto déclenchée (SF {bien.score_fiabilite:.1f}%)",
                    metadonnees=f"Score départ: {bien.score_fiabilite:.1f}%, Seuil critique: {SEUIL_SCORE_CRITIQUE}%"
                )

                # Notification hors transaction
                try:
                    techniciens = self.db.query(Utilisateur).join(Role).filter(Role.nom == "TECHNICIEN").all()
                    if techniciens:
                        designation = f"{getattr(bien, 'marque', '') or getattr(bien, 'fabricant', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
                        self.notification_service.envoyer_notification(
                            ids_destinataires=[t.id for t in techniciens],
                            type_notif=TypeNotificationEnum.MAINTENANCE_ALERTE,
                            titre=f"⚠️ Maintenance préventive automatique - {designation}",
                            contenu=f"Une maintenance préventive a été automatiquement planifiée pour le bien {designation} (Score de fiabilité: {bien.score_fiabilite:.1f}%)",
                            lien=f"/maintenances/{nouvelle_maintenance.id_maintenance}"
                        )
                except Exception as e:
                    logger.error(f"Erreur envoi notification maintenance auto: {e}")

                return nouvelle_maintenance

        return None

    def verifier_et_creer_alerte_vnc(self, bien_id: int) -> Optional[AlerteVNC]:
        """
        Vérifie si le bien atteint un seuil VNC critique
        et crée une alerte si nécessaire.
        """
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien {bien_id} non trouvé")

        if bien.vnc_alerte_declenchee:
            return None

        ratio_vnc = bien.ratio_vnc_restante
        prix_acquisition = float(bien.prix_acquisition) if bien.prix_acquisition else 0
        vnc = bien.valeur_nette_comptable

        seuil = SEUIL_VNC_CRITIQUE if bien.est_critique else SEUIL_VNC_STANDARD
        seuil_ratio = seuil / 100

        if ratio_vnc <= seuil_ratio:
            try:
                with self.db.begin():
                    alerte = AlerteVNC(
                        bien_id=bien_id,
                        seuil_atteint=f"{seuil}%",
                        ratio_vnc=ratio_vnc,
                        valeur_vnc=vnc,
                        valeur_origine=prix_acquisition,
                        statut=StatutAlerteVNC.EN_ATTENTE,
                        description=f"Le bien a atteint le seuil VNC critique de {seuil}% (VNC: {vnc:.2f} USD, Ratio: {ratio_vnc*100:.1f}%)"
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
                metadonnees=f"Ratio: {ratio_vnc*100:.1f}%, Valeur origine: {prix_acquisition:.2f}"
            )

            # Notification hors transaction
            try:
                responsables = self.db.query(Utilisateur).join(Role).filter(
                    Role.nom.in_(['DG', 'COMPTABLE'])
                ).all()
                if responsables:
                    designation = f"{getattr(bien, 'marque', '') or getattr(bien, 'fabricant', '')} {getattr(bien, 'modele', '')}".strip() or f"Bien #{bien_id}"
                    self.notification_service.envoyer_notification(
                        ids_destinataires=[u.id for u in responsables],
                        type_notif=TypeNotificationEnum.ALERTE_VNC,
                        titre=f"🚨 Alerte VNC - {designation}",
                        contenu=f"Le bien {designation} a atteint le seuil VNC critique de {seuil}% (VNC: {vnc:.2f} USD). Remplacement recommandé.",
                        lien=f"/alertes-vnc/{alerte.id}"
                    )
            except Exception as e:
                logger.error(f"Erreur envoi notification alerte VNC: {e}")

            return alerte

        return None

    # ============================================================
    # PROJECTIONS (SYNCHRONE — UN SEUL BIEN)
    # ============================================================

    def generer_projections_bien(self, bien_id: int) -> List[ProjectionInvestissement]:
        """
        Calcule les projections d'investissement pour un bien sur N+1 à N+5.
        Cette méthode est appelée par la tâche CRON.
        """
        bien = self.db.query(Bien).filter(Bien.id_bien == bien_id).first()
        if not bien:
            raise ValueError(f"Bien {bien_id} non trouvé")

        try:
            with self.db.begin():
                # Supprimer les anciennes projections
                self.db.query(ProjectionInvestissement).filter(
                    ProjectionInvestissement.bien_id == bien_id
                ).delete()

                annee_actuelle = datetime.now(timezone.utc).year
                prix_acquisition = float(bien.prix_acquisition) if bien.prix_acquisition else 0

                type_bien = bien.type_bien or "AUTRE"
                taux_obsolescence = TAUX_OBSOLESCENCE_DEFAUT.get(type_bien, TAUX_OBSOLESCENCE_DEFAUT["AUTRE"])

                projections = []

                for i in range(ANNEE_PROJECTION_DEBUT, ANNEE_PROJECTION_FIN + 1):
                    annee_projection = annee_actuelle + i

                    if bien.score_fiabilite is not None:
                        score_projete = max(0, bien.score_fiabilite - (i * (100 / (ANNEE_PROJECTION_FIN + 1))))
                    else:
                        score_projete = 100 - (i * (100 / (ANNEE_PROJECTION_FIN + 1)))

                    vnc_projetee = prix_acquisition * (1 - (i / 10))
                    vnc_projetee = max(0, vnc_projetee)

                    critere_fin_amortissement = vnc_projetee <= 0
                    critere_score_fiabilite = score_projete < SEUIL_SCORE_CRITIQUE

                    cout_remplacement = prix_acquisition * (1 + (i * 0.03))

                    projection = ProjectionInvestissement(
                        bien_id=bien_id,
                        annee_projection=annee_projection,
                        date_fin_vie_estimee=datetime(annee_projection, 12, 31, tzinfo=timezone.utc),
                        critere_fin_amortissement=critere_fin_amortissement,
                        critere_score_fiabilite=critere_score_fiabilite,
                        critere_obligation_legale=False,
                        critere_remplacement_cyclique=False,
                        cout_remplacement_estime=cout_remplacement,
                        score_fiabilite_projete=score_projete,
                        vnc_projetee=vnc_projetee,
                        taux_obsolescence=taux_obsolescence,
                        statut=StatutProjection.ESTIMEE,
                        date_calcul=datetime.now(timezone.utc)
                    )

                    self.db.add(projection)
                    projections.append(projection)

        except SQLAlchemyError as e:
            logger.error(f"Erreur génération projections bien {bien_id}: {e}")
            raise ValueError(f"Échec de la génération des projections: {str(e)}")

        self._journaliser_evenement(
            bien_id=bien_id,
            type_evenement=TypeEvenementImmobilisation.ACQUISITION,
            libelle=f"Projections d'investissement calculées pour N+1 à N+{ANNEE_PROJECTION_FIN}",
            metadonnees=f"Taux obsolescence: {taux_obsolescence}%"
        )

        return projections

    # ============================================================
    # MÉTHODES DÉPORTÉES (NE PLUS UTILISER DIRECTEMENT)
    # ============================================================

    def calculer_tous_les_scores(self) -> dict:
        """
        🔴 DÉPRÉCIÉ — Utiliser la tâche CRON cron_scores.py
        
        Cette méthode parcourt tous les biens et est trop lourde 
        pour un appel synchrone.
        """
        logger.warning(
            "calculer_tous_les_scores est dépréciée. "
            "Utiliser la tâche CRON pour le calcul batch."
        )
        raise RuntimeError(
            "Méthode dépréciée. Utiliser la tâche de fond cron_scores."
        )

    def calculer_toutes_les_projections(self) -> dict:
        """
        🔴 DÉPRÉCIÉ — Utiliser la tâche CRON cron_projections.py
        """
        logger.warning(
            "calculer_toutes_les_projections est dépréciée. "
            "Utiliser la tâche CRON."
        )
        raise RuntimeError(
            "Méthode dépréciée. Utiliser la tâche de fond cron_projections."
        )

    def calculer_projections_investissement(self, *args, **kwargs):
        """
        🔴 DÉPRÉCIÉ — Utiliser generer_projections_bien()
        """
        logger.warning(
            "calculer_projections_investissement est dépréciée. "
            "Utiliser generer_projections_bien() pour un seul bien."
        )
        raise RuntimeError(
            "Méthode dépréciée. Utiliser generer_projections_bien() ou la tâche CRON."
        )

    # ============================================================
    # MÉTHODE UTILITAIRE — JOURNALISATION
    # ============================================================

    def _journaliser_evenement(
        self,
        bien_id: int,
        type_evenement: TypeEvenementImmobilisation,
        libelle: str,
        montant: float = 0.0,
        utilisateur_id: int = None,
        metadonnees: str = None
    ):
        """
        Journalise un événement dans le journal des immobilisations.
        ✅ N'utilise PAS de transaction — appelée hors des blocs with db.begin()
        ✅ En cas d'échec, loggue l'erreur sans lever d'exception
        """
        try:
            journal = JournalEvenementImmobilisation(
                bien_id=bien_id,
                type_evenement=type_evenement,
                date_evenement=datetime.now(timezone.utc),
                libelle=libelle,
                montant=montant,
                utilisateur_id=utilisateur_id,
                metadonnees=metadonnees
            )
            self.db.add(journal)
            self.db.commit()
        except Exception as e:
            # 🔴 Ne pas rollback — laisser la transaction parente gérer
            logger.error(f"Erreur lors de la journalisation: {e}")
            # Ne pas lever d'exception pour ne pas bloquer l'opération principale