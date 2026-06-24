from asyncio.log import logger

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from ..models.maintenance import Maintenance, TypeMaintenance, StatutMaintenance
from ..models.bien import Bien, EtatBien
from ..models.panne import Panne, StatutPanne
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..schemas.maintenance import MaintenanceCreate, MaintenanceUpdate
from ..services.notification_service import NotificationService
from ..models.notification import TypeNotificationEnum
from ..services.bien_service import BienService

class MaintenanceService:
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
        self.bien_service = BienService(db)
    
    def planifier_maintenance(self, data: MaintenanceCreate, id_technicien: int) -> Maintenance:
        """Planifie une nouvelle maintenance"""
        bien = self.db.query(Bien).filter(Bien.id_bien == data.id_bien).first()
        if not bien:
            raise ValueError(f"Bien {data.id_bien} non trouvé")
        
        # ✅ CORRECTION : Utiliser datetime.now(timezone.utc) pour comparer avec des datetime aware
        now = datetime.now(timezone.utc)
        date_planifiee = data.date_planifiee 
        # Si la date est naive, la convertir en aware UTC
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
            statut=StatutMaintenance.PLANIFIEE
        )
        self.db.add(maintenance)
        self.db.commit()
        self.db.refresh(maintenance)
        
        # 🆕 NOTIFICATION: Alerter tous les techniciens
        try:
            techniciens = self.db.query(Utilisateur).join(Role).filter(Role.nom == "TECHNICIEN").all()
            if techniciens:
                self.notification_service.envoyer_notification(
                    ids_destinataires=[t.id for t in techniciens],  # ✅ Liste d'IDs
                    type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                    titre=f"🔧 Nouvelle maintenance planifiée - {getattr(bien, 'marque', '') or getattr(bien, 'fabricant', '')}",
                    contenu=f"Une maintenance {data.type_maintenance.value} est planifiée le {data.date_planifiee.strftime('%d/%m/%Y')} pour le bien {getattr(bien, 'marque', '') or getattr(bien, 'fabricant', '')} {getattr(bien, 'modele', '')}",
                    lien=f"/maintenances/{maintenance.id_maintenance}"
                )
        except Exception as e:
            logger.error(f"Erreur envoi notification maintenance: {e}")
        
        return maintenance
    
    def get_maintenances_by_bien(self, id_bien: int, skip: int = 0, limit: int = 100) -> List[Maintenance]:
        return self.db.query(Maintenance).filter(
            Maintenance.id_bien == id_bien
        ).order_by(Maintenance.date_planifiee.desc()).offset(skip).limit(limit).all()

    def get_maintenances_by_panne(self, id_panne: int) -> List[Maintenance]:
        return (
            self.db.query(Maintenance)
            .filter(Maintenance.id_panne == id_panne)
            .order_by(Maintenance.date_creation.desc())
            .all()
        )
    
    def get_maintenances_by_technicien(self, id_technicien: int, statut: Optional[str] = None) -> List[Maintenance]:
        """Récupère les maintenances assignées à un technicien"""
        query = self.db.query(Maintenance).filter(Maintenance.id_technicien == id_technicien)
        if statut:
            query = query.filter(Maintenance.statut == statut)
        return query.order_by(Maintenance.date_planifiee.asc()).all()
    
    def get_maintenances_a_venir(self, jours: int = 7) -> List[Maintenance]:
        """Récupère les maintenances planifiées dans les X jours"""
        now = datetime.now(timezone.utc)
        date_limite = now + timedelta(days=jours)
        return self.db.query(Maintenance).filter(
            Maintenance.statut == StatutMaintenance.PLANIFIEE,
            Maintenance.date_planifiee <= date_limite,
            Maintenance.date_planifiee >= now
        ).order_by(Maintenance.date_planifiee.asc()).all()
    
    def get_maintenances_en_retard(self) -> List[Maintenance]:
        """Récupère les maintenances planifiées non réalisées et en retard"""
        now = datetime.now(timezone.utc)
        return self.db.query(Maintenance).filter(
            Maintenance.statut == StatutMaintenance.PLANIFIEE,
            Maintenance.date_planifiee < now
        ).order_by(Maintenance.date_planifiee.asc()).all()
    
    def get_maintenance(self, id_maintenance: int) -> Optional[Maintenance]:
        """Récupère une maintenance par son ID"""
        return self.db.query(Maintenance).filter(Maintenance.id_maintenance == id_maintenance).first()
    
    def update_maintenance(self, id_maintenance: int, data: MaintenanceUpdate) -> Optional[Maintenance]:
        """Met à jour une maintenance"""
        maintenance = self.get_maintenance(id_maintenance)
        if not maintenance:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(maintenance, field, value)
        self.db.commit()
        self.db.refresh(maintenance)
        return maintenance
    
    def demarrer_maintenance(self, id_maintenance: int) -> Optional[Maintenance]:
        """Démarre une intervention"""
        maintenance = self.get_maintenance(id_maintenance)
        if not maintenance:
            return None
        if maintenance.statut != StatutMaintenance.PLANIFIEE:
            raise ValueError(f"Impossible de démarrer une maintenance en statut {maintenance.statut.value}")
        maintenance.demarrer()
        self.db.commit()
        self.db.refresh(maintenance)
        return maintenance
    
    def terminer_maintenance(self, id_maintenance: int, rapport: str, cout: float, pieces_remplacees: str = None) -> Optional[Maintenance]:
        """Termine une intervention"""
        maintenance = (
            self.db.query(Maintenance)
            .options(joinedload(Maintenance.panne), joinedload(Maintenance.bien))
            .filter(Maintenance.id_maintenance == id_maintenance)
            .first()
        )
        if not maintenance:
            return None
        if maintenance.statut not in [StatutMaintenance.PLANIFIEE, StatutMaintenance.EN_COURS]:
            raise ValueError(f"Impossible de terminer une maintenance en statut {maintenance.statut.value}")

        maintenance.terminer(rapport, cout)
        if pieces_remplacees:
            maintenance.pieces_remplacees = pieces_remplacees

        bien = maintenance.bien
        designation = (
            f"{getattr(bien, 'marque', '') or getattr(bien, 'fabricant', '')} "
            f"{getattr(bien, 'modele', '')}"
        ).strip() if bien else f"Bien #{maintenance.id_bien}"

        if maintenance.type_maintenance == TypeMaintenance.CORRECTIVE and maintenance.id_panne:
            self.bien_service.changer_etat_bien(maintenance.id_bien, EtatBien.EN_TEST, commit=False)
            panne = maintenance.panne or self.db.query(Panne).filter(
                Panne.id_panne == maintenance.id_panne
            ).first()
            if panne:
                panne.changer_statut(StatutPanne.EN_TEST)
            self.notification_service.envoyer_notification(
                ids_destinataires=maintenance.id_technicien,
                type_notif=TypeNotificationEnum.BIEN_EN_TEST,
                titre=f"✅ Maintenance terminée - Phase de test",
                contenu=(
                    f"La maintenance corrective sur le bien {designation} est terminée. "
                    "Le bien est maintenant en phase de test. Veuillez confirmer la résolution "
                    "de la panne après validation."
                ),
                lien=f"/pannes/{maintenance.id_panne}",
            )
        else:
            nouvel_etat = EtatBien.BON
            if bien and bien.etat == EtatBien.USAGE:
                nouvel_etat = EtatBien.USAGE
            self.bien_service.changer_etat_bien(maintenance.id_bien, nouvel_etat, commit=False)

        self.db.commit()
        self.db.refresh(maintenance)

        if maintenance.type_maintenance == TypeMaintenance.PREVENTIVE and maintenance.periodicite_jours:
            self._planifier_prochaine_maintenance_preventive(maintenance)

        return maintenance
    
    def _planifier_prochaine_maintenance_preventive(self, maintenance: Maintenance):
        """Planifie automatiquement la prochaine maintenance préventive"""
        nouvelle_date = maintenance.date_fin_reelle + timedelta(days=maintenance.periodicite_jours)
        prochaine_maintenance = Maintenance(
            id_bien=maintenance.id_bien,
            id_technicien=maintenance.id_technicien,
            type_maintenance=TypeMaintenance.PREVENTIVE,
            date_planifiee=nouvelle_date,
            description=f"Maintenance périodique - {maintenance.description}",
            periodicite_jours=maintenance.periodicite_jours,
            statut=StatutMaintenance.PLANIFIEE
        )
        self.db.add(prochaine_maintenance)
        self.db.commit()
    
    def reporter_maintenance(self, id_maintenance: int, nouvelle_date: datetime, motif: str = None) -> Optional[Maintenance]:
        """Reporte une maintenance à une date ultérieure"""
        maintenance = self.get_maintenance(id_maintenance)
        if not maintenance:
            return None
        if maintenance.statut not in [StatutMaintenance.PLANIFIEE]:
            raise ValueError(f"Impossible de reporter une maintenance en statut {maintenance.statut.value}")
        
        now = datetime.now(timezone.utc)
        # Si la nouvelle date est naive, la convertir en aware UTC
        if nouvelle_date.tzinfo is None:
            nouvelle_date = nouvelle_date.replace(tzinfo=timezone.utc)
        
        if nouvelle_date < now:
            raise ValueError("La nouvelle date ne peut pas être dans le passé")
        
        maintenance.reporter(nouvelle_date, motif)
        self.db.commit()
        self.db.refresh(maintenance)
        return maintenance
    
    def annuler_maintenance(self, id_maintenance: int) -> Optional[Maintenance]:
        """Annule une maintenance"""
        maintenance = self.get_maintenance(id_maintenance)
        if not maintenance:
            return None
        if maintenance.statut not in [StatutMaintenance.PLANIFIEE]:
            raise ValueError(f"Impossible d'annuler une maintenance en statut {maintenance.statut.value}")
        
        maintenance.statut = StatutMaintenance.ANNULEE
        self.db.commit()
        self.db.refresh(maintenance)
        return maintenance
    
    def get_statistiques(self, annee: int = None) -> dict:
        """Retourne les statistiques des maintenances"""
        query = self.db.query(Maintenance)
        if annee:
            query = query.filter(func.extract('year', Maintenance.date_creation) == annee)
        
        total = query.count()
        
        # Statistiques par type
        par_type = {}
        for t in TypeMaintenance:
            count = query.filter(Maintenance.type_maintenance == t).count()
            if count > 0:
                par_type[t.value] = count
        
        # Statistiques par statut
        par_statut = {}
        for s in StatutMaintenance:
            count = query.filter(Maintenance.statut == s).count()
            if count > 0:
                par_statut[s.value] = count
        
        # Coûts
        cout_total = query.filter(Maintenance.cout > 0).with_entities(func.sum(Maintenance.cout)).scalar() or 0
        cout_moyen = cout_total / total if total > 0 else 0
        
        # Taux de réalisation
        terminees = query.filter(Maintenance.statut == StatutMaintenance.TERMINEE).count()
        taux_realisation = (terminees / total * 100) if total > 0 else 0
        
        # Alertes (maintenances en retard)
        alertes = self.get_maintenances_en_retard_count()
        
        return {
            "total_maintenances": total,
            "par_type": par_type,
            "par_statut": par_statut,
            "cout_total_annee": cout_total,
            "cout_moyen": cout_moyen,
            "taux_realisation": round(taux_realisation, 2),
            "alertes": alertes
        }
    
    def get_maintenances_en_retard_count(self) -> int:
        """Nombre de maintenances en retard"""
        now = datetime.now(timezone.utc)
        return self.db.query(Maintenance).filter(
            Maintenance.statut == StatutMaintenance.PLANIFIEE,
            Maintenance.date_planifiee < now
        ).count()
    
    def calculer_duree_vie_bien(self, id_bien: int) -> dict:
        """Calcule la durée de vie d'un bien basée sur ses maintenances"""
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
        
        # Dernière maintenance terminée
        dernieres_terminees = [m for m in maintenances if m.statut == StatutMaintenance.TERMINEE]
        derniere_maintenance = max(dernieres_terminees, key=lambda m: m.date_fin_reelle) if dernieres_terminees else None
        
        # Prochaine maintenance planifiée
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