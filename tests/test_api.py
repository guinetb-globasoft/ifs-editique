import time

import pytest
from fastapi.testclient import TestClient

from app import generations, main
from app.ifs import sso
from tests.conftest import chromium_disponible


@pytest.fixture
def client(lecteur, monkeypatch, tmp_path):
    # Le jeton présenté est relayé à un LecteurIFS : on le remplace par le jeu enregistré.
    monkeypatch.setattr(main, "LecteurIFS", lambda **_: lecteur)
    # Le journal des générations des tests ne se mêle pas à celui de l'application.
    monkeypatch.setattr(generations, "FICHIER", tmp_path / "generations.jsonl")
    return TestClient(main.app)


def test_sante_sans_session(client):
    reponse = client.get("/sante")
    assert reponse.status_code == 200 and "version" in reponse.json()


def test_navigateur_sans_jeton_renvoye_au_realm(client):
    reponse = client.get("/commande-achat/C106553", headers={"Accept": "text/html"},
                         follow_redirects=False)
    assert reponse.status_code == 307
    assert reponse.headers["location"] == "/auth/ifs/login?retour=/commande-achat/C106553"


def test_appel_api_sans_jeton_refuse(client):
    assert client.get("/commande-achat/C106553/donnees").status_code == 401


def test_donnees_avec_jeton_porteur(client):
    reponse = client.get("/commande-achat/C106553/donnees", headers={"Authorization": "Bearer x"})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["commande"]["numero"] == "C106553"
    assert corps["commande"]["logo"].endswith("octets")
    assert corps["appels_ifs"] and all("Bearer" not in str(a) for a in corps["appels_ifs"])


def test_commande_inconnue(client):
    reponse = client.get("/commande-achat/X999/donnees", headers={"Authorization": "Bearer x"})
    assert reponse.status_code == 404


@pytest.mark.skipif(not chromium_disponible(), reason="Chromium de Playwright non installé")
def test_pdf_avec_jeton_porteur(client):
    reponse = client.get("/commande-achat/C106553", headers={"Authorization": "Bearer x"})
    assert reponse.status_code == 200
    assert reponse.headers["content-type"] == "application/pdf"
    assert reponse.content.startswith(b"%PDF")
    assert 'inline; filename="Commande_C106553.pdf"' == reponse.headers["content-disposition"]
    assert "ifs;dur=" in reponse.headers["server-timing"]


@pytest.mark.skipif(not chromium_disponible(), reason="Chromium de Playwright non installé")
def test_chaque_generation_consignee_avec_ses_temps(client):
    client.get("/commande-achat/C106553", headers={"Authorization": "Bearer x"})
    client.get("/commande-achat/X999", headers={"Authorization": "Bearer x"})
    [echec, reussie] = generations.lire()
    assert (reussie["numero"], reussie["statut"], reussie["pages"]) == ("C106553", "ok", 2)
    assert reussie["duree_totale_s"] >= reussie["duree_lecture_ifs_s"] + reussie["duree_pdf_s"] - 0.01
    assert reussie["appels_ifs"] > 0 and reussie["appel_le_plus_lent"]["chemin"]
    assert (echec["numero"], echec["statut"]) == ("X999", "introuvable")

    page = client.get("/generations", headers={"Authorization": "Bearer x"})
    assert page.status_code == 200 and "C106553" in page.text and "médiane" in page.text
    donnees = client.get("/generations?format=json", headers={"Authorization": "Bearer x"}).json()
    assert donnees["statistiques"]["reussies"] == 1


def test_journal_reserve_aux_utilisateurs_ifs(client):
    assert client.get("/generations").status_code == 401


# ------------------------------------------------------------------- SSO
@pytest.mark.parametrize("demande, attendu", [
    ("/commande-achat/C1", "/commande-achat/C1"),
    ("https://ailleurs.example/vol", "/"),
    ("//ailleurs.example/vol", "/"),
    (None, "/"),
])
def test_pas_de_redirection_ouverte(demande, attendu):
    assert sso.retour_sur(demande) == attendu


def test_jeton_expire_rafraichi_une_seule_fois(monkeypatch):
    appels = []

    def faux_realm(donnees):
        appels.append(donnees["grant_type"])
        return {"access_token": "nouveau", "expires_in": 180,
                "refresh_token": "r2", "refresh_expires_in": 1800}

    monkeypatch.setattr(sso, "_appeler_token", faux_realm)
    sso._jetons["sid"] = sso.Jeton("ancien", expire_a=time.time() - 1, refresh_token="r1",
                                   refresh_expire_a=time.time() + 600)
    assert sso.jeton_de_session("sid").access_token == "nouveau"
    assert sso.jeton_de_session("sid").access_token == "nouveau"
    assert appels == ["refresh_token"]


def test_session_perimee_oubliee(monkeypatch):
    sso._jetons["vieux"] = sso.Jeton("a", expire_a=time.time() - 1, refresh_token="r",
                                     refresh_expire_a=time.time() - 1)
    assert sso.jeton_de_session("vieux") is None and "vieux" not in sso._jetons
