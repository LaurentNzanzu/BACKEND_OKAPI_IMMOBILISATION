from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from datetime import datetime

from ..models.panne import Panne, StatutPanne
from ..models.bien import Bien, EtatBien
from ..models.maintenance import Maintenance, TypeMaintenance, StatutMaintenance
from ..models.utilisateur import Utilisateur
from ..models.role import Role
from ..models.notification import TypeNotificationEnum
from ..schemas.panne import PanneCreate, PanneUpdate
from .bien_service import BienService
from .notification_service import NotificationService
from .audit_service import AuditService


def _bien_designation(bien: Bien) -> str:
    label = (
        f"{getattr(bien, 'marque', None) or getattr(bien, 'fabricant', None) or ''} "
        f"{getattr(bien, 'modele', '')}"
    ).strip()
    return label or f"Bien #{bien.id_bien}"


class PanneService:
    def __init__(self, db: Session):
        self.db = db
        self.bien_service = BienService(db)
        self.notification_service = NotificationService(db)
        self.audit_service = AuditService(db)

    def _verifier_technicien(self, id_technicien: int) -> Utilisateur:
        technicien = (
            self.db.query(Utilisateur)
            .options(joinedload(Utilisateur.role))
            .filter(Utilisateur.id == id_technicien)
            .first()
        )
        if not technicien:
            raise ValueError("Technicien invalide")
        if not technicien.role or technicien.role.nom.upper() != "TECHNICIEN":
            raise ValueError("Seul un technicien peut effectuer cette action")
        return technicien

    def _creer_maintenance_corrective(self, panne: Panne, id_technicien: int) -> Maintenance:
        description = (
            f"Maintenance corrective suite à la panne #{panne.id_panne} - "
            f"{panne.description[:200]}"
        )
        maintenance = Maintenance(
            id_bien=panne.id_bien,
            id_technicien=id_technicien,
            id_panne=panne.id_panne,
            type_maintenance=TypeMaintenance.CORRECTIVE,
            statut=StatutMaintenance.PLANIFIEE,
            date_planifiee=datetime.utcnow(),
            description=description,
            periodicite_jours=None,
        )
        self.db.add(maintenance)
        return maintenance

    def declarer_panne(self, data: PanneCreate, id_technicien: int) -> Panne:
        self._verifier_technicien(id_technicien)

        bien = self.db.query(Bien).filter(Bien.id_bien == data.id_bien).first()
        if not bien:
            raise ValueError(f"Bien {data.id_bien} non trouvé")
        if bien.etat == EtatBien.MAINTENANCE:
            raise ValueError("Une panne ne peut pas être déclarée sur un bien déjà en maintenance")
        if bien.etat == EtatBien.REFORME:
            raise ValueError("Une panne ne peut pas être déclarée sur un bien réformé")

        try:
            panne = Panne(
                id_bien=data.id_bien,
                id_technicien=id_technicien,
                type_panne=data.type_panne,
                priorite=data.priorite,
                description=data.description,
                diagnostic=data.diagnostic,
                statut=StatutPanne.DECLAREE,
                date_declaration=datetime.utcnow(),
            )
            self.db.add(panne)
            self.db.flush()

            self._creer_maintenance_corrective(panne, id_technicien)
            self.bien_service.changer_etat_bien(data.id_bien, EtatBien.MAINTENANCE, commit=False)

            self.db.commit()
            self.db.refresh(panne)

            designation = _bien_designation(bien)
            techniciens = (
                self.db.query(Utilisateur).join(Role).filter(Role.nom == "TECHNICIEN").all()
            )
            if techniciens:
                self.notification_service.envoyer_notification(
                    ids_destinataires=[t.id for t in techniciens],
                    type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                    titre=f"🔧 Nouvelle panne déclarée - {designation}",
                    contenu=(
                        f"Une panne de type {data.type_panne.value} a été déclarée sur le bien "
                        f"{designation}. Priorité: {data.priorite.value}. "
                        "Une maintenance corrective a été créée."
                    ),
                    lien=f"/pannes/{panne.id_panne}",
                )

            gestionnaires = (
                self.db.query(Utilisateur)
                .join(Role)
                .filter(Role.nom.in_(["GESTIONNAIRE", "ADMIN"]))
                .all()
            )
            if gestionnaires:
                self.notification_service.envoyer_notification(
                    ids_destinataires=[g.id for g in gestionnaires],
                    type_notif=TypeNotificationEnum.MAINTENANCE_PLANIFIEE,
                    titre=f"🔧 Panne déclarée - {designation}",
                    contenu=(
                        f"Une panne {data.type_panne.value} (priorité {data.priorite.value}) "
                        f"a été déclarée sur {designation}."
                    ),
                    lien=f"/pannes/{panne.id_panne}",
                )

            return panne
        except Exception:
            self.db.rollback()
            raise

    def resoudre_panne(self, id_panne: int, id_technicien: int) -> Panne:
        self._verifier_technicien(id_technicien)

        panne = (
            self.db.query(Panne)
            .options(joinedload(Panne.bien), joinedload(Panne.maintenances))
            .filter(Panne.id_panne == id_panne)
            .first()
        )
        if not panne:
            raise ValueError("Panne non trouvée")
        if panne.statut != StatutPanne.EN_TEST:
            raise ValueError(
                f"La panne doit être en phase de test (statut actuel: {panne.statut.value})"
            )

        maintenances = [
            m for m in panne.maintenances
            if m.type_maintenance == TypeMaintenance.CORRECTIVE
        ]
        if not maintenances:
            raise ValueError("Aucune maintenance corrective associée à cette panne")

        maintenance_terminee = any(
            m.statut == StatutMaintenance.TERMINEE for m in maintenances
        )
        if not maintenance_terminee:
            raise ValueError("La maintenance corrective associée n'est pas terminée")

        try:
            panne.changer_statut(StatutPanne.TERMINEE)
            self.bien_service.changer_etat_bien(panne.id_bien, EtatBien.BON, commit=False)

            self.db.commit()
            self.db.refresh(panne)

            bien = panne.bien
            designation = _bien_designation(bien) if bien else f"Bien #{panne.id_bien}"

            gestionnaires = (
                self.db.query(Utilisateur)
                .join(Role)
                .filter(Role.nom.in_(["GESTIONNAIRE", "ADMIN"]))
                .all()
            )
            if gestionnaires:
                self.notification_service.envoyer_notification(
                    ids_destinataires=[g.id for g in gestionnaires],
                    type_notif=TypeNotificationEnum.PANNE_RESOLUE,
                    titre=f"✅ Panne résolue - {designation}",
                    contenu=(
                        f"La panne #{panne.id_panne} sur le bien {designation} est résolue. "
                        "Le bien est à nouveau opérationnel."
                    ),
                    lien=f"/pannes/{panne.id_panne}",
                )

            self.audit_service.log_update(
                user_id=id_technicien,
                table_name="pannes",
                record_id=panne.id_panne,
                old_values={"statut": StatutPanne.EN_TEST.value},
                new_values={"statut": StatutPanne.TERMINEE.value, "bien": EtatBien.BON.value},
            )

            return panne
        except Exception:
            self.db.rollback()
            raise

    def get_pannes_by_bien(self, id_bien: int) -> List[Panne]:
        return self.db.query(Panne).filter(Panne.id_bien == id_bien).order_by(Panne.date_declaration.desc()).all()

    def get_pannes_by_technicien(self, id_technicien: int, statut: Optional[str] = None) -> List[Panne]:
        query = self.db.query(Panne).filter(Panne.id_technicien == id_technicien)
        if statut:
            query = query.filter(Panne.statut == statut)
        return query.order_by(Panne.priorite.desc(), Panne.date_declaration.asc()).all()

    def get_panne(self, id_panne: int) -> Optional[Panne]:
        return self.db.query(Panne).filter(Panne.id_panne == id_panne).first()

    def update_panne(self, id_panne: int, data: PanneUpdate) -> Optional[Panne]:
        panne = self.get_panne(id_panne)
        if not panne:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(panne, field, value)
        self.db.commit()
        self.db.refresh(panne)
        return panne

    def changer_statut(self, id_panne: int, nouveau_statut: StatutPanne) -> Optional[Panne]:
        panne = self.get_panne(id_panne)
        if not panne:
            return None
        panne.changer_statut(nouveau_statut)
        self.db.commit()
        self.db.refresh(panne)
        return panne

    def get_pannes_actives(self) -> List[Panne]:
        return self.db.query(Panne).filter(
            Panne.statut.in_([
                StatutPanne.DECLAREE,
                StatutPanne.DIAGNOSTIQUEE,
                StatutPanne.EN_ATTENTE_PIECES,
                StatutPanne.EN_VALIDATION,
                StatutPanne.EN_COURS,
                StatutPanne.EN_TEST,
            ])
        ).order_by(Panne.priorite.desc(), Panne.date_declaration.asc()).all()

    def get_statistiques(self, id_bien: Optional[int] = None) -> dict:
        query = self.db.query(Panne)
        if id_bien:
            query = query.filter(Panne.id_bien == id_bien)
        total = query.count()
        en_cours = query.filter(Panne.statut == StatutPanne.EN_COURS).count()
        terminees = query.filter(Panne.statut == StatutPanne.TERMINEE).count()
        return {
            "total_pannes": total,
            "en_cours": en_cours,
            "terminees": terminees,
            "taux_resolution": round((terminees / total * 100) if total > 0 else 0, 2),
        }
