# backend/app/services/permission_service.py
# -*- coding: utf-8 -*-
"""
PermissionService — Contrôle d'accès granulaire (RBAC)
Sprint 0 — Fondations multi-tenant OKAPI Flotte

Méthodes principales :
- hasPermission(user, permission_code) : méthode centrale réutilisable
- CRUD permissions (creer, obtenir, lister, modifier, supprimer)
- Gestion Role ↔ Permission (attribuer, revoquer, lister)
"""
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from ..models.permission import Permission, role_permissions
from ..models.role import Role
from ..models.utilisateur import Utilisateur
from ..services.audit_service import AuditService

logger = logging.getLogger(__name__)


class PermissionService:
    """Service central de gestion des permissions granulaires (RBAC)."""

    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)

    # ============================================================
    # 1. MÉTHODE CENTRALE D'AUTORISATION
    # ============================================================

    def hasPermission(self, user: Optional[Utilisateur], permission_code: str) -> bool:
        """
        Méthode centrale d'autorisation réutilisable dans tous les endpoints.
        
        Règles :
        - ADMIN a TOUS les droits (super admin plateforme)
        - Sinon, vérifie que le rôle de l'utilisateur possède la permission active
        
        Args:
            user: Utilisateur connecté (peut être None)
            permission_code: Code de la permission (ex: "MISSION_CREATE")
        
        Returns:
            bool: True si autorisé, False sinon
        """
        if not user:
            return False

        if not permission_code or not isinstance(permission_code, str):
            logger.warning("permission_code invalide ou vide")
            return False

        # Récupérer le rôle (singulier en priorité, sinon pluriel)
        role = getattr(user, "role", None)
        if not role:
            roles = getattr(user, "roles", None)
            if roles:
                try:
                    role = roles[0] if isinstance(roles, list) else list(roles)[0]
                except (IndexError, TypeError):
                    role = None

        if not role:
            logger.debug(f"Aucun rôle pour l'utilisateur {getattr(user, 'id', '?')}")
            return False

        role_nom = (getattr(role, "nom", "") or "").strip().upper()

        # ADMIN a tous les droits
        if role_nom == "ADMIN":
            return True

        # Vérifier que la permission existe et est active
        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            logger.debug(f"Permission '{permission_code}' introuvable")
            return False

        if not permission.actif:
            logger.debug(f"Permission '{permission_code}' désactivée")
            return False

        # Vérifier si le rôle possède la permission
        try:
            role_permissions_noms = {
                (p.nom or "").strip().upper()
                for p in (role.permissions or [])
            }
        except Exception as e:
            logger.error(f"Erreur lecture role.permissions : {e}")
            return False

        return permission_code.strip().upper() in role_permissions_noms

    def verifier_permissions_utilisateur(
        self, user: Optional[Utilisateur], permissions_codes: List[str], require_all: bool = False
    ) -> bool:
        """
        Vérifie si un utilisateur possède plusieurs permissions.
        
        Args:
            user: Utilisateur connecté
            permissions_codes: Liste de codes de permissions
            require_all: Si True, l'utilisateur doit avoir TOUTES les permissions.
                         Si False, il doit en avoir AU MOINS UNE.
        """
        if not permissions_codes:
            return False

        resultats = [self.hasPermission(user, code) for code in permissions_codes]
        return all(resultats) if require_all else any(resultats)

    # ============================================================
    # 2. CRUD PERMISSIONS
    # ============================================================

    def creer_permission(
        self,
        nom: str,
        module: str,
        action: str,
        description: Optional[str] = None,
        actif: bool = True,
        user_id: Optional[int] = None,
    ) -> Permission:
        """
        Crée une nouvelle permission.
        Le champ `nom` doit être unique (format recommandé : "module:action").
        """
        nom_clean = (nom or "").strip()
        if not nom_clean:
            raise ValueError("Le nom de la permission est obligatoire")

        # Vérifier l'unicité
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

        # Audit
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

        logger.info(f"Permission créée : {permission.nom}")
        return permission

    def obtenir_permission(self, id_permission: int) -> Optional[Permission]:
        """Récupère une permission par son ID."""
        return (
            self.db.query(Permission)
            .filter(Permission.id_permission == id_permission)
            .first()
        )

    def obtenir_permission_par_nom(self, nom: str) -> Optional[Permission]:
        """Récupère une permission par son nom unique."""
        if not nom:
            return None
        return (
            self.db.query(Permission)
            .filter(Permission.nom == nom.strip())
            .first()
        )

    def lister_permissions(
        self,
        module: Optional[str] = None,
        actif: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> List[Permission]:
        """Liste les permissions avec filtres optionnels."""
        query = self.db.query(Permission)

        if module:
            query = query.filter(Permission.module == module.strip())

        if actif is not None:
            query = query.filter(Permission.actif == actif)

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                (Permission.nom.ilike(term))
                | (Permission.description.ilike(term))
            )

        return query.order_by(Permission.module, Permission.action).all()

    def lister_modules(self) -> List[str]:
        """Retourne la liste des modules distincts."""
        rows = (
            self.db.query(Permission.module)
            .distinct()
            .order_by(Permission.module)
            .all()
        )
        return [r[0] for r in rows if r[0]]

    def mettre_a_jour_permission(
        self,
        id_permission: int,
        data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Permission:
        """Met à jour une permission."""
        permission = self.obtenir_permission(id_permission)
        if not permission:
            raise ValueError(f"Permission #{id_permission} introuvable")

        old_values = {
            "nom": permission.nom,
            "description": permission.description,
            "module": permission.module,
            "action": permission.action,
            "actif": permission.actif,
        }

        # Champs autorisés à la modification
        champs_autorises = ["description", "module", "action", "actif"]
        for champ in champs_autorises:
            if champ in data and data[champ] is not None:
                setattr(permission, champ, data[champ])

        self.db.flush()

        # Audit
        if user_id:
            try:
                self.audit_service.log_update(
                    user_id=user_id,
                    table_name="permissions",
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

    def supprimer_permission(
        self, id_permission: int, user_id: Optional[int] = None
    ) -> bool:
        """
        Supprime une permission (détache automatiquement des rôles via CASCADE).
        """
        permission = self.obtenir_permission(id_permission)
        if not permission:
            raise ValueError(f"Permission #{id_permission} introuvable")

        old_values = {
            "nom": permission.nom,
            "module": permission.module,
            "action": permission.action,
        }
        nom_permission = permission.nom

        self.db.delete(permission)
        self.db.flush()

        # Audit
        if user_id:
            try:
                self.audit_service.log_delete(
                    user_id=user_id,
                    table_name="permissions",
                    record_id=id_permission,
                    old_values=old_values,
                )
            except Exception as e:
                logger.warning(f"Audit delete permission échoué : {e}")

        logger.info(f"Permission supprimée : {nom_permission}")
        return True

    # ============================================================
    # 3. GESTION ROLE ↔ PERMISSION
    # ============================================================

    def attribuer_permission(
        self,
        role_id: int,
        permission_code: str,
        user_id: Optional[int] = None,
    ) -> bool:
        """
        Attribue une permission à un rôle.
        Idempotent : ne fait rien si déjà attribuée.
        """
        role = self.db.query(Role).filter(Role.id_role == role_id).first()
        if not role:
            raise ValueError(f"Rôle #{role_id} introuvable")

        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            raise ValueError(f"Permission '{permission_code}' introuvable")

        # Vérifier si déjà attribuée
        existing = self.db.execute(
            role_permissions.select().where(
                (role_permissions.c.id_role == role_id)
                & (role_permissions.c.id_permission == permission.id_permission)
            )
        ).first()

        if existing:
            logger.debug(
                f"Permission '{permission_code}' déjà attribuée au rôle {role.nom}"
            )
            return False

        # Insérer dans la table d'association
        self.db.execute(
            role_permissions.insert().values(
                id_role=role_id,
                id_permission=permission.id_permission,
            )
        )
        self.db.flush()

        # Audit
        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="role_permissions",
                    record_id=role_id,
                    action="ATTRIBUTION_PERMISSION",
                    nouvelles_valeurs={
                        "role_id": role_id,
                        "role_nom": role.nom,
                        "permission_id": permission.id_permission,
                        "permission_nom": permission.nom,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit attribution permission échoué : {e}")

        logger.info(
            f"Permission '{permission_code}' attribuée au rôle '{role.nom}'"
        )
        return True

    def revoquer_permission(
        self,
        role_id: int,
        permission_code: str,
        user_id: Optional[int] = None,
    ) -> bool:
        """
        Révoque une permission d'un rôle.
        Idempotent : ne fait rien si non attribuée.
        """
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
            logger.debug(
                f"Permission '{permission_code}' non attribuée au rôle {role.nom}"
            )
            return False

        # Audit
        if user_id:
            try:
                self.audit_service.log_action(
                    user_id=user_id,
                    table_name="role_permissions",
                    record_id=role_id,
                    action="REVOCATION_PERMISSION",
                    anciennes_valeurs={
                        "role_id": role_id,
                        "role_nom": role.nom,
                        "permission_id": permission.id_permission,
                        "permission_nom": permission.nom,
                    },
                )
            except Exception as e:
                logger.warning(f"Audit révocation permission échoué : {e}")

        logger.info(
            f"Permission '{permission_code}' révoquée du rôle '{role.nom}'"
        )
        return True

    def lister_permissions_role(self, role_id: int) -> List[Permission]:
        """Liste toutes les permissions attribuées à un rôle."""
        role = self.db.query(Role).filter(Role.id_role == role_id).first()
        if not role:
            raise ValueError(f"Rôle #{role_id} introuvable")

        return list(role.permissions or [])

    def lister_roles_par_permission(self, permission_code: str) -> List[Role]:
        """Liste tous les rôles possédant une permission donnée."""
        permission = self.obtenir_permission_par_nom(permission_code)
        if not permission:
            return []
        return list(permission.roles or [])

    def obtenir_utilisateurs_par_permission(
        self, permission_code: str
    ) -> List[Utilisateur]:
        """
        Récupère tous les utilisateurs dont le rôle possède la permission.
        Utile pour les notifications ciblées par permission.
        """
        roles = self.lister_roles_par_permission(permission_code)
        if not roles:
            return []

        role_ids = [r.id_role for r in roles]
        return (
            self.db.query(Utilisateur)
            .filter(Utilisateur.role_id.in_(role_ids))
            .all()
        )

    # ============================================================
    # 4. MÉTHODES UTILITAIRES (seed, vérifications)
    # ============================================================

    def permission_existe(self, permission_code: str) -> bool:
        """Vérifie si une permission existe."""
        return self.obtenir_permission_par_nom(permission_code) is not None

    def compter_permissions_role(self, role_id: int) -> int:
        """Compte le nombre de permissions d'un rôle."""
        return (
            self.db.query(role_permissions)
            .filter(role_permissions.c.id_role == role_id)
            .count()
        )

    def obtenir_ou_creer_permission(
        self,
        nom: str,
        module: str,
        action: str,
        description: Optional[str] = None,
        actif: bool = True,
    ) -> Permission:
        """
        Récupère une permission ou la crée si elle n'existe pas.
        Utile pour les scripts de seed.
        """
        existing = self.obtenir_permission_par_nom(nom)
        if existing:
            return existing
        return self.creer_permission(
            nom=nom,
            module=module,
            action=action,
            description=description,
            actif=actif,
        )