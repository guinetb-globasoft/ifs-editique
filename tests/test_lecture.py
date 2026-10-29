"""La forme des requêtes envoyées à IFS, sans IFS : on capture l'URL au lieu d'appeler."""

from __future__ import annotations

import pytest

from app.ifs import lecture
from app.ifs.lecture import LecteurIFS


class _Reponse:
    ok, status_code = True, 200

    def json(self):
        return {"value": []}


@pytest.fixture
def urls(monkeypatch) -> list[str]:
    appelees: list[str] = []

    def get(url, **_kwargs):
        appelees.append(url)
        return _Reponse()

    monkeypatch.setattr(lecture.requests, "get", get)
    return appelees


def test_espaces_du_filtre_en_pourcent_20_jamais_en_plus(urls):
    # IFS répond 400 « Demande mal formée » à `Company+eq+'GAE'` (constaté sur CFG le 29/10/2026)
    LecteurIFS(jeton="j", base="https://ifs/v1").lire("X.svc/Set", {"$filter": "Company eq 'GAE'", "$select": "A,B"})
    assert urls == ["https://ifs/v1/X.svc/Set?$filter=Company%20eq%20%27GAE%27&$select=A%2CB"]
    assert "+" not in urls[0]


def test_parametres_ajoutes_a_une_requete_existante(urls):
    LecteurIFS(jeton="j", base="https://ifs/v1").lire("X.svc/Set?$top=1", {"$filter": "A eq 1"})
    assert urls == ["https://ifs/v1/X.svc/Set?$top=1&$filter=A%20eq%201"]
