"""Tests unitaires des permissions biens (sans base de données)."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.bien_permissions import (  # noqa: E402
    can_view_biens,
    can_view_financial_data,
    can_create_bien,
    can_delete_bien,
    can_edit_bien_full,
    can_edit_bien_technician,
    can_technician_view_bien,
    can_view_bien_detail,
    filter_bien_update,
    sanitize_bien_dict,
    build_bien_context_dict,
)
from app.models.bien import EtatBien
from app.schemas.bien import BienUpdate, EtatBienEnum


def _user(role_name: str, user_id: int = 1):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(nom=role_name))


class TestBienPermissionsRoles:
    def test_technicien_view_without_financial(self):
        user = _user("TECHNICIEN")
        assert can_view_biens(user) is True
        assert can_view_financial_data(user) is False
        assert can_create_bien(user) is False
        assert can_delete_bien(user) is False
        assert can_edit_bien_full(user) is False
        assert can_edit_bien_technician(user) is True

    def test_magasinier_no_bien_access(self):
        user = _user("MAGASINIER")
        assert can_view_biens(user) is False

    def test_gestionnaire_full_bien_rights(self):
        user = _user("GESTIONNAIRE")
        assert can_view_financial_data(user) is True
        assert can_delete_bien(user) is True
        assert can_edit_bien_full(user) is True

    def test_comptable_no_delete(self):
        user = _user("COMPTABLE")
        assert can_create_bien(user) is True
        assert can_delete_bien(user) is False


class TestSanitizeBienDict:
    def test_strips_financial_fields_for_technicien(self):
        user = _user("TECHNICIEN")
        data = {
            "id_bien": 1,
            "marque": "Toyota",
            "prix_acquisition": 15000,
            "date_acquisition": "2020-01-01",
            "cumul_amortissement": 2000,
            "statut_comptable": "ACTIF",
        }
        result = sanitize_bien_dict(data, user)
        assert result["marque"] == "Toyota"
        assert "prix_acquisition" not in result
        assert "cumul_amortissement" not in result
        assert "statut_comptable" not in result

    def test_keeps_financial_fields_for_comptable(self):
        user = _user("COMPTABLE")
        data = {"prix_acquisition": 15000}
        result = sanitize_bien_dict(data, user)
        assert result["prix_acquisition"] == 15000


class TestFilterBienUpdate:
    def test_technicien_only_allowed_fields(self):
        user = _user("TECHNICIEN")
        update = BienUpdate(
            etat=EtatBienEnum.PANNE,
            localisation="Atelier B",
            prix_acquisition=99999,
            date_acquisition="2020-01-01",
            marque="Renault",
        )
        filtered = filter_bien_update(user, update)
        dumped = filtered.model_dump(exclude_unset=True)
        assert dumped.get("etat") == EtatBienEnum.PANNE
        assert dumped.get("localisation") == "Atelier B"
        assert dumped.get("marque") == "Renault"
        assert "prix_acquisition" not in dumped
        assert "date_acquisition" not in dumped

    def test_gestionnaire_full_update(self):
        user = _user("GESTIONNAIRE")
        update = BienUpdate(prix_acquisition=12000, etat=EtatBienEnum.BON)
        filtered = filter_bien_update(user, update)
        dumped = filtered.model_dump(exclude_unset=True)
        assert dumped.get("prix_acquisition") == 12000
        assert dumped.get("etat") == EtatBienEnum.BON


class TestTechnicianBienAccess:
    def _bien(self, bien_id=1, etat=EtatBien.BON):
        return SimpleNamespace(id_bien=bien_id, etat=etat)

    def _db_with_panne(self, panne):
        db = MagicMock()
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = panne
        db.query.return_value = query
        return db

    def test_technicien_can_view_bien_en_panne(self):
        user = _user("TECHNICIEN")
        bien = self._bien(etat=EtatBien.PANNE)
        db = self._db_with_panne(None)
        assert can_technician_view_bien(user, bien, db) is True

    def test_technicien_can_view_bien_via_assigned_panne(self):
        user = _user("TECHNICIEN", user_id=5)
        bien = self._bien(etat=EtatBien.BON)
        panne = SimpleNamespace(id_panne=10, id_bien=1, id_technicien=5)
        db = self._db_with_panne(panne)
        assert can_technician_view_bien(user, bien, db, panne_id=10) is True

    def test_technicien_can_view_bien_via_panne_context_even_if_not_assignee(self):
        """Contexte panne : accès si le technicien a une autre panne sur le même bien."""
        user = _user("TECHNICIEN", user_id=5)
        bien = self._bien(etat=EtatBien.BON)
        panne_context = SimpleNamespace(id_panne=10, id_bien=1, id_technicien=99)
        own_panne = SimpleNamespace(id_panne=11, id_bien=1, id_technicien=5)

        db = MagicMock()
        query = MagicMock()
        query.filter.return_value = query
        query.first.side_effect = [panne_context, own_panne]
        db.query.return_value = query

        assert can_technician_view_bien(user, bien, db, panne_id=10) is True

    def test_technicien_denied_unrelated_bien(self):
        user = _user("TECHNICIEN", user_id=5)
        bien = self._bien(etat=EtatBien.BON)
        db = self._db_with_panne(None)
        assert can_view_bien_detail(user, bien, db) is False

    def test_bien_context_excludes_financial_fields(self):
        user = _user("TECHNICIEN")
        bien = SimpleNamespace(
            id_bien=1,
            type_bien="vehicule",
            marque="Toyota",
            fabricant=None,
            modele="Hilux",
            numero_serie=None,
            immatriculation="ABC-123",
            localisation="Atelier",
            etat=EtatBien.PANNE,
            qr_code="VEH-1",
            prix_acquisition=50000,
            date_acquisition="2020-01-01",
        )
        context = build_bien_context_dict(bien, user)
        assert context["marque"] == "Toyota"
        assert "prix_acquisition" not in context
        assert "date_acquisition" not in context
