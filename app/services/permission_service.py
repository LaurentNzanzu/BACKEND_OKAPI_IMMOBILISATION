# backend/app/services/permission_service.py
# -*- coding: utf-8 -*-
"""
PermissionService — Contrôle d'accès granulaire (RBAC) avec override par ONG
Phase 4 — Cascade : Super Admin → Module → Override ONG → Défaut global

- Méthodes publiques conservées : hasPermission, creer_permission, etc.
- Nouvelles méthodes : attribuer_permission_ong, revoquer_permission_ong,
                       resoudre_permission_ong
"""
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from ..models.permission import Permission, role_permissions
from ..models.role import Role
from ..models.utilisateur import Utilisateur
from ..models.organisation import Organisation
from ..models.organisation_role_permission import OrganisationRolePermission
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


class PermissionService:
    """Service central de gestion des permissions granulaires (RBAC)."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)

    # ============================================================
    # 1. MÉTHODE CENTRALE D'AUTORISATION (CASCADE)
    # ============================================================

    def hasPermission(self, user: Optional[Utilisateur], permission_code: str) -> bool:
        """
        Cascade de résolution :
        1. Pas d'utilisateur → False
        2. ADMIN plateforme (organisation_id NULL + rôle ADMIN) → True
        3. Sinon, récupérer le rôle + org_id
        4. ADMIN (ONG) → True (dans son ONG)
        5. Vérifier la permission existe + active
        6. Chercher override ONG → appliquer `accorde`
        7. Sinon → appliquer le défaut global (role_permissions)
        """
        if not user:
            return False

        if not permission_code or not isinstance(permission_code, str):
            logger.warning("permission_code invalide ou vide")
            return False

        code = permission_code.strip().upper()

        # Récupérer le rôle
        role = getattr(user, "role", None)
        if not role:
            roles = getattr(user, "roles", None)
            if roles:
                try:
                    role = roles[0] if isinstance(roles, list) else list(roles)[0]
                except (IndexError, TypeError):
                    role = None

        if not role:
            return False

        role_nom = (getattr(role, "nom", "") or "").strip().upper()
        role_id = getattr(role, "id_role", None)
        org_id = getattr(user, "organisation_id", None)

        # ADMIN plateforme (org_id NULL) → tout autorisé
        if role_nom == "ADMIN" and org_id is None:
            return True

        # ADMIN ONG → tout autorisé dans son ONG
        if role_nom == "ADMIN" and org_id is not None:
            return True

        # Sans rôle_id, on ne peut pas résoudre
        if not role_id:
            return False

        # Vérifier que la permission existe et est active
        permission = self.obtenir_permission_par_nom(code)
        if not permission or not permission.actif:
            return False

        # Si pas d'organisation → défaut global uniquement
        if org_id is None:
            return self._role_a_permission_defaut(role, code)

        # ÉTAPE 1 : Chercher un override pour cette ONG
        override = (
            self.db.query(OrganisationRolePermission)
            .filter(
                OrganisationRolePermission.organisation_id == org_id,
                OrganisationRolePermission.id_role == role_id,
                OrganisationRolePermission.id_permission == permission.id_permission,
            )
            .first()
        )
        if override is not None:
            return bool(override.accorde)

        # ÉTAPE 2 : Aucun override → défaut global
        return self._role_a_permission_defaut(role, code)

    def _role_a_permission_defaut(self, role: Role, permission_code: str) -> bool:
        """Vérifie la permission dans la table globale role_permissions."""
        try:
            role_permissions_noms = {
                (p.nom or "").strip().upper()
                for p in (role.permissions or [])
            }
        except Exception as e:
            logger.error(f"Erreur lecture role.permissions : {e}")
            return False
        return permission_code.strip().upper() in role_permissions_noms

    def resoudre_permission_ong(
        self, organisation_id: int, id_role: int, permission_code: str
    ) -> Dict[str, Any]:
        """
        Diagnostic : explique comment une permission est résolue pour une ONG.
        Retourne : {source, accorde, override_existe}
        """
        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            return {
                "permission_code": permission_code,
                "organisation_id": organisation_id,
                "id_role": id_role,
                "source": "not_found",
                "accorde": False,
                "override_existe": False,
            }

        override = (
            self.db.query(OrganisationRolePermission)
            .filter(
                OrganisationRolePermission.organisation_id == organisation_id,
                OrganisationRolePermission.id_role == id_role,
                OrganisationRolePermission.id_permission == permission.id_permission,
            )
            .first()
        )

        if override is not None:
            return {
                "permission_code": permission_code,
                "organisation_id": organisation_id,
                "id_role": id_role,
                "source": "override",
                "accorde": bool(override.accorde),
                "override_existe": True,
            }

        # Défaut global
        role = self.db.query(Role).filter(Role.id_role == id_role).first()
        accorde = False
        if role:
            accorde = self._role_a_permission_defaut(role, permission_code)

        return {
            "permission_code": permission_code,
            "organisation_id": organisation_id,
            "id_role": id_role,
            "source": "global_default",
            "accorde": accorde,
            "override_existe": False,
        }

    # ============================================================
    # 2. OVERRIDE PAR ONG (NOUVELLES MÉTHODES)
    # ============================================================

    def attribuer_permission_ong(
        self,
        organisation_id: int,
        id_role: int,
        permission_code: str,
        accorde: bool = True,
        user_id: Optional[int] = None,
    ) -> OrganisationRolePermission:
        """
        Crée ou met à jour un override : (organisation, role, permission) → accorde
        Idempotent : si l'override existe déjà, met à jour la valeur.
        """
        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            raise ValueError(f"Permission '{permission_code}' introuvable")

        role = self.db.query(Role).filter(Role.id_role == id_role).first()
        if not role:
            raise ValueError(f"Rôle #{id_role} introuvable")

        existing = (
            self.db.query(OrganisationRolePermission)
            .filter(
                OrganisationRolePermission.organisation_id == organisation_id,
                OrganisationRolePermission.id_role == id_role,
                OrganisationRolePermission.id_permission == permission.id_permission,
            )
            .first()
        )

        if existing:
            old_val = existing.accorde
            existing.accorde = bool(accorde)
            override = existing
        else:
            override = OrganisationRolePermission(
                organisation_id=organisation_id,
                id_role=id_role,
                id_permission=permission.id_permission,
                accorde=bool(accorde),
            )
            self.db.add(override)

        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="organisation_role_permissions",
                    record_id=override.id,
                    action="OVERRIDE_PERMISSION",
                    nouvelles_valeurs={
                        "organisation_id": organisation_id,
                        "id_role": id_role,
                        "permission": permission_code,
                        "accorde": bool(accorde),
                    },
                )
            except Exception as e:
                logger.warning(f"Audit override échoué : {e}")

        logger.info(
            f"Override permission '{permission_code}' pour ONG #{organisation_id}, "
            f"rôle #{id_role} → accorde={accorde}"
        )
        return override

    def revoquer_override_permission(
        self,
        organisation_id: int,
        id_role: int,
        permission_code: str,
        user_id: Optional[int] = None,
    ) -> bool:
        """Supprime un override (retour au défaut global)."""
        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            raise ValueError(f"Permission '{permission_code}' introuvable")

        override = (
            self.db.query(OrganisationRolePermission)
            .filter(
                OrganisationRolePermission.organisation_id == organisation_id,
                OrganisationRolePermission.id_role == id_role,
                OrganisationRolePermission.id_permission == permission.id_permission,
            )
            .first()
        )
        if not override:
            return False

        self.db.delete(override)
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_delete(
                    user_id=user_id,
                    table_name="organisation_role_permissions",
                    record_id=override.id,
                    old_values={
                        "organisation_id": organisation_id,
                        "id_role": id_role,
                        "permission": permission_code,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit révocation override échoué : {e}")

        return True

    def lister_overrides_ong(self, organisation_id: int, id_role: Optional[int] = None):
        """Liste tous les overrides d'une ONG (optionnellement filtrés par rôle)."""
        query = self.db.query(OrganisationRolePermission).filter(
            OrganisationRolePermission.organisation_id == organisation_id
        )
        if id_role is not None:
            query = query.filter(OrganisationRolePermission.id_role == id_role)
        return query.all()

    # ============================================================
    # 3. MÉTHODES EXISTANTES (conservées intactes)
    # ============================================================

    def verifier_permissions_utilisateur(
        self, user: Optional[Utilisateur], permissions_codes: List[str], require_all: bool = False
    ) -> bool:
        if not permissions_codes:
            return False
        resultats = [self.hasPermission(user, code) for code in permissions_codes]
        return all(resultats) if require_all else any(resultats)

    def creer_permission(
        self,
        nom: str,
        module: str,
        action: str,
        description: Optional[str] = None,
        actif: bool = True,
        user_id: Optional[int] = None,
    ) -> Permission:
        nom_clean = (nom or "").strip()
        if not nom_clean:
            raise ValueError("Le nom de la permission est obligatoire")
        existing = self.obtenir_permission_par_nom(nom_clean)
        if existing:
            raise ValueError(f"Une permission avec le nom '{nom_clean}' existe déjà")
        if not module or not action:
            raise ValueError("Le module et l'action sont obligatoires")

        permission = Permission(
            nom=nom_clean,
            description=description,
            module=module.strip(),
            action=action.strip(),
            actif=actif,
        )
        self.db.add(permission)
        self.db.flush()

        if user_id:
            try:
                self.audit_service.log_create(
                    user_id=user_id,
                    table_name="permissions",
                    record_id=permission.id_permission,
                    new_values={
                        "nom": permission.nom,
                        "module": permission.module,
                        "action": permission.action,
                        "actif": permission.actif,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit creation permission échoué : {e}")
        return permission

    def obtenir_permission(self, id_permission: int) -> Optional[Permission]:
        return self.db.query(Permission).filter(Permission.id_permission == id_permission).first()

    def obtenir_permission_par_nom(self, nom: str) -> Optional[Permission]:
        if not nom:
            return None
        return self.db.query(Permission).filter(Permission.nom == nom.strip()).first()

    def lister_permissions(
        self,
        module: Optional[str] = None,
        actif: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> List[Permission]:
        query = self.db.query(Permission)
        if module:
            query = query.filter(Permission.module == module.strip())
        if actif is not None:
            query = query.filter(Permission.actif == actif)
        if search:
            term = f"%{search.strip()}%"
            query = query.filter((Permission.nom.ilike(term)) | (Permission.description.ilike(term)))
        return query.order_by(Permission.module, Permission.action).all()

    def lister_modules(self) -> List[str]:
        rows = self.db.query(Permission.module).distinct().order_by(Permission.module).all()
        return [r[0] for r in rows if r[0]]

    def mettre_a_jour_permission(
        self, id_permission: int, data: Dict[str, Any], user_id: Optional[int] = None
    ) -> Permission:
        permission = self.obtenir_permission(id_permission)
        if not permission:
            raise ValueError(f"Permission #{id_permission} introuvable")
        old_values = {
            "description": permission.description,
            "module": permission.module,
            "action": permission.action,
            "actif": permission.actif,
        }
        for champ in ["description", "module", "action", "actif"]:
            if champ in data and data[champ] is not None:
                setattr(permission, champ, data[champ])
        self.db.flush()
        if user_id:
            try:
                self.audit_service.log_update(
                    user_id=user_id, table_name="permissions",
                    record_id=permission.id_permission,
                    old_values=old_values,
                    new_values={
                        "description": permission.description,
                        "module": permission.module,
                        "action": permission.action,
                        "actif": permission.actif,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit update permission échoué : {e}")
        return permission

    def supprimer_permission(self, id_permission: int, user_id: Optional[int] = None) -> bool:
        permission = self.obtenir_permission(id_permission)
        if not permission:
            raise ValueError(f"Permission #{id_permission} introuvable")
        old_values = {"nom": permission.nom, "module": permission.module, "action": permission.action}
        nom_permission = permission.nom
        self.db.delete(permission)
        self.db.flush()
        if user_id:
            try:
                self.audit_service.log_delete(
                    user_id=user_id, table_name="permissions",
                    record_id=id_permission, old_values=old_values,
                )
            except Exception as e:
                logger.warning(f"Audit delete permission échoué : {e}")
        logger.info(f"Permission supprimée : {nom_permission}")
        return True

    def attribuer_permission(
        self, role_id: int, permission_code: str, user_id: Optional[int] = None
    ) -> bool:
        role = self.db.query(Role).filter(Role.id_role == role_id).first()
        if not role:
            raise ValueError(f"Rôle #{role_id} introuvable")
        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            raise ValueError(f"Permission '{permission_code}' introuvable")
        existing = self.db.execute(
            role_permissions.select().where(
                (role_permissions.c.id_role == role_id)
                & (role_permissions.c.id_permission == permission.id_permission)
            )
        ).first()
        if existing:
            return False
        self.db.execute(
            role_permissions.insert().values(id_role=role_id, id_permission=permission.id_permission)
        )
        self.db.flush()
        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id, table_name="role_permissions", record_id=role_id,
                    action="ATTRIBUTION_PERMISSION",
                    nouvelles_valeurs={"role_id": role_id, "permission_nom": permission.nom},
                )
            except Exception as e:
                logger.warning(f"Audit attribution permission échoué : {e}")
        return True

    def revoquer_permission(
        self, role_id: int, permission_code: str, user_id: Optional[int] = None
    ) -> bool:
        role = self.db.query(Role).filter(Role.id_role == role_id).first()
        if not role:
            raise ValueError(f"Rôle #{role_id} introuvable")
        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            raise ValueError(f"Permission '{permission_code}' introuvable")
        result = self.db.execute(
            role_permissions.delete().where(
                (role_permissions.c.id_role == role_id)
                & (role_permissions.c.id_permission == permission.id_permission)
            )
        )
        self.db.flush()
        if result.rowcount == 0:
            return False
        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id, table_name="role_permissions", record_id=role_id,
                    action="REVOCATION_PERMISSION",
                    anciennes_valeurs={"role_id": role_id, "permission_nom": permission.nom},
                )
            except Exception as e:
                logger.warning(f"Audit révocation permission échoué : {e}")
        return True

    def lister_permissions_role(self, role_id: int) -> List[Permission]:
        role = self.db.query(Role).filter(Role.id_role == role_id).first()
        if not role:
            raise ValueError(f"Rôle #{role_id} introuvable")
        return list(role.permissions or [])

    def lister_roles_par_permission(self, permission_code: str) -> List[Role]:
        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            return []
        return list(permission.roles or [])

    def obtenir_utilisateurs_par_permission(self, permission_code: str) -> List[Utilisateur]:
        roles = self.lister_roles_par_permission(permission_code)
        if not roles:
            return []
        role_ids = [r.id_role for r in roles]
        return self.db.query(Utilisateur).filter(Utilisateur.role_id.in_(role_ids)).all()

    def permission_existe(self, permission_code: str) -> bool:
        return self.obtenir_permission_par_nom(permission_code) is not None

    def compter_permissions_role(self, role_id: int) -> int:
        return (
            self.db.query(role_permissions).filter(role_permissions.c.id_role == role_id).count()
        )

    def obtenir_ou_creer_permission(
        self,
        nom: str,
        module: str,
        action: str,
        description: Optional[str] = None,
        actif: bool = True,
    ) -> Permission:
        existing = self.obtenir_permission_par_nom(nom)
        if existing:
            return existing
        return self.creer_permission(nom=nom, module=module, action=action, description=description, actif=actif)