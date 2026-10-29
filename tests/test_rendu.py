import io

import pytest
from pypdf import PdfReader

from app.editiques.commande_achat import generer, lire_commande, rendre_html
from tests.conftest import CLE, chromium_disponible

NBSP = " "


def test_html_porte_les_valeurs_du_bon(lecteur):
    corps = rendre_html(lire_commande(lecteur, lecteur, "C106553")).corps
    for attendu in ("BON DE COMMANDE N° C106553", "EN DATE DU 14/10/2026", "REVISION N&#186; 0",
                    "GA ENTREPRISE SAS", "SIRET : 42826603500123", "Mode de règlement : VIREMENT SEPA",
                    f"2{NBSP}000,00{NBSP}€", "MONTANT TOTAL HT EN EUROS", "Prix fermes nets et non révisables",
                    "Nom et signature du fournisseur"):
        assert attendu in corps, attendu


def test_brouillon(lecteur):
    lecteur.reponses[CLE]["Objstate"] = "Planned"
    corps = rendre_html(lire_commande(lecteur, lecteur, "C106553")).corps
    assert "BROUILLON DE COMMANDE C106553" in corps
    assert "BON DE COMMANDE N°" not in corps.split("<body>")[1]


def test_valeurs_ifs_echappees(lecteur):
    lecteur.reponses[CLE]["LabelNote"] = "<script>alert(1)</script>"
    corps = rendre_html(lire_commande(lecteur, lecteur, "C106553")).corps
    assert "<script>alert" not in corps and "&lt;script&gt;" in corps


def test_pied_de_page_numerote_et_logo_en_tete(lecteur):
    document = rendre_html(lire_commande(lecteur, lecteur, "C106553"))
    assert 'class="pageNumber"' in document.pied and 'class="totalPages"' in document.pied
    assert "Capital : 9 107 300 €" in document.pied
    assert "data:image/png;base64," in document.entete


@pytest.mark.skipif(not chromium_disponible(), reason="Chromium de Playwright non installé")
def test_pdf_bon_puis_cga(lecteur):
    generation = generer(lecteur, lecteur, "C106553")
    pages = PdfReader(io.BytesIO(generation.contenu)).pages
    assert generation.pages == 2
    assert generation.duree_lecture_s >= 0 and generation.duree_pdf_s > 0
    # 2 pages de bon de commande (comme Armony pour C106553), puis les 3 pages de la CGA.
    assert len(pages) == 5
    texte = pages[0].extract_text()
    assert "BON DE COMMANDE N° C106553" in texte and "1/2" in texte
    assert "Nom et signature du client" in pages[1].extract_text()


@pytest.mark.skipif(not chromium_disponible(), reason="Chromium de Playwright non installé")
def test_pdf_signe_de_l_application_et_de_sa_version(lecteur):
    from app.version import VERSION
    proprietes = PdfReader(io.BytesIO(generer(lecteur, lecteur, "C106553").contenu)).metadata
    assert proprietes["/Title"] == "Bon de commande C106553"
    assert proprietes["/Creator"] == proprietes["/Producer"] == f"ifs-app-editique {VERSION}"
