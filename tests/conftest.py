"""Fixtures communes : un lecteur IFS rejoué depuis exemples/commande_C106553.json.

Aucun test n'appelle IFS ni le realm : ce qu'ils prouvent, c'est la règle et la
mise en page, pas les noms d'API (voir docs/specs/commande-achat.md, « Vérifié »).
"""

from __future__ import annotations

import copy
import functools
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app.ifs.enregistre import LecteurEnregistre  # noqa: E402

JEU = RACINE / "exemples" / "commande_C106553.json"
CLE = "PurchaseOrderHandling.svc/PurchaseOrderSet(OrderNo='C106553')"


@pytest.fixture
def lecteur() -> LecteurEnregistre:
    """Un lecteur neuf à chaque test : on peut modifier ses réponses sans effet de bord."""
    origine = LecteurEnregistre.depuis_fichier(JEU)
    return LecteurEnregistre(copy.deepcopy(origine.reponses), dict(origine.binaires))


@functools.cache
def chromium_disponible() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False
