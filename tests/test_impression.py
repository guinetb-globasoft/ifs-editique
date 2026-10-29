"""Le point d'entrée d'IFS à l'impression (aux adresses d'Armony), sans IFS : un faux IFS en mémoire."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import generations, impression, main
from app.ifs import ecriture

APERCU = "/GetDownload.aspx?layout_name=ReportPreview.axdata&RESULT_KEY_=56607&PRINT_JOB_ID_=47479&USER_ID_=BENGUI"
OK = ("/Execute.aspx?layout_name=ReportOk.axdata&&AxAsync=True&&RESULT_KEY_=56607&&PRINT_JOB_ID_=47479"
      "&&USER_ID_=BENGUI&&LANGUAGE_CODE_=fr&&LAYOUT_NAME_=PurchaseOrderPrintRepArmony.rdl"
      "&&LOCALE_LANGUAGE_=fr&&LOCALE_COUNTRY_=FR&&COPIES_=1")
ARCHIVE_BDC = {"ResultKey": 56607, "ReportId": "PURCHASE_ORDER_PRINT_REP", "Notes": "N° cde: C105125",
               "EventParams": "!PDF\n$PDF_EVENT_PARAM_1=\n$PDF_EVENT_PARAM_6=C105125\n$REPLY_TO_USER=EDWTRI\n"}


class FauxIFS:
    """Lectures servies par chemin ; écritures notées dans l'ordre."""

    def __init__(self, archive: dict):
        self.archive = archive
        self.ecritures: list[tuple] = []
        self.travaux = {47479: {"PrintJobId": 47479, "PrinterId": "NO_PRINTOUT", "@odata.etag": "W/e1",
                                "Settings": "!PDF\n$SEND_PDF=TRUE\n$SEND_PDF_TO=fournisseur@exemple.fr\n"}}

    # côté lecteur
    def lire(self, chemin, params=None):
        filtre = (params or {}).get("$filter", "")
        if chemin == "ReportArchive.svc/ArchiveSet":
            return [self.archive]
        if chemin == "PrintDialog.svc/PdfArchiveSet":
            travail = int(filtre.rsplit(" ", 1)[1])
            return [{"Id": f"pdf-{travail}", "PrintJobId": travail, "@odata.etag": f"W/p{travail}",
                     "LayoutName": impression.DISPOSITION}]
        if chemin == "ReportArchive.svc/PrintJobSet":
            if "Message eq" in filtre:
                return [{"PrintJobId": 47500}]
            return [self.travaux[int(filtre.rsplit(" ", 1)[1])]]
        raise AssertionError(chemin)

    # côté écrivain
    def remplacer_pdf(self, cle, id_pdf, etag, contenu):
        self.ecritures.append(("pdf", cle, id_pdf, etag, contenu))

    def supprimer_travail(self, travail, etag):
        self.ecritures.append(("supprimer", travail, etag))

    def evenement(self, evenement, valeurs):
        self.ecritures.append(("evenement", evenement, dict(valeurs)))


GENERATION = SimpleNamespace(contenu=b"%PDF-notre", pages=2, duree_lecture_s=1.0, duree_pdf_s=0.5,
                             commande=SimpleNamespace(avertissements=[]))


@pytest.fixture
def ifs(monkeypatch, tmp_path):
    faux = FauxIFS(dict(ARCHIVE_BDC))
    monkeypatch.setattr(impression, "_technique", lambda: (faux, faux))
    monkeypatch.setattr(impression, "_generer", lambda lecteur, numero: GENERATION)
    monkeypatch.setattr(generations, "FICHIER", tmp_path / "generations.jsonl")
    return faux


@pytest.fixture
def relais(monkeypatch):
    appels: list[dict] = []

    def requete(methode, url, **options):
        appels.append({"methode": methode, "url": url, **options})
        return SimpleNamespace(content=b"armony", status_code=200, headers={"content-type": "text/plain"})

    monkeypatch.setattr(impression, "_relais", lambda: "https://armony.exemple/AxData_Rec")
    monkeypatch.setattr(impression.requests, "request", requete)
    return appels


@pytest.fixture
def client():
    return TestClient(main.app)


def test_apercu_d_un_bon_de_commande_remplace_le_pdf_du_travail(client, ifs, relais):
    reponse = client.get(APERCU)
    assert reponse.status_code == 200
    assert ifs.ecritures == [("pdf", 56607, "pdf-47479", "W/p47479", b"%PDF-notre")]
    assert relais == []


def test_apercu_d_une_autre_editique_relaye_tel_quel_a_armony(client, ifs, relais):
    ifs.archive = {"ResultKey": 56607, "ReportId": "APP_FOR_PAYMENT_REP"}
    reponse = client.get(APERCU)
    assert reponse.status_code == 200 and reponse.content == b"armony"
    assert relais[0]["url"] == "https://armony.exemple/AxData_Rec/GetDownload.aspx?" + APERCU.split("?", 1)[1]
    assert ifs.ecritures == []


def test_agent_aurena_toujours_relaye(client, ifs, relais):
    reponse = client.post("/Execute.aspx?layout_name=ReportAurenaAgent.axdata&&PRINT_JOB_ID_=1", content=b"<msg/>")
    assert reponse.status_code == 200
    assert relais[0]["methode"] == "POST" and relais[0]["data"] == b"<msg/>"
    assert relais[0]["url"].endswith("/Execute.aspx?layout_name=ReportAurenaAgent.axdata&&PRINT_JOB_ID_=1")


def test_ok_suit_le_connecteur_armony_dans_l_ordre(ifs):
    parametres = {"RESULT_KEY_": "56607", "PRINT_JOB_ID_": "47479", "USER_ID_": "BENGUI", "LANGUAGE_CODE_": "fr",
                  "LAYOUT_NAME_": impression.DISPOSITION, "LOCALE_LANGUAGE_": "fr", "LOCALE_COUNTRY_": "FR"}
    details = impression.ok(parametres)
    supprimer, travail, pdf_, imprime = ifs.ecritures
    assert supprimer == ("supprimer", 47479, "W/e1")
    assert travail[1] == "ARMONY_REPORT_JOB" and travail[2]["PRINTER_ID"] == "NO_PRINTOUT"
    assert travail[2]["RESULT_KEY"] == 56607 and len(travail[2]["PRINT_JOB_GUID"]) == 36
    # le PDF va au travail créé par ARMONY_REPORT_JOB, pas à celui qu'IFS avait envoyé
    assert pdf_ == ("pdf", 56607, "pdf-47500", "W/p47500", b"%PDF-notre")
    assert imprime == ("evenement", "ARMONY_REPORT_PRINT",
                       {"PRINTER_ID": "NO_PRINTOUT", "RESULT_KEY": 56607, "PRINT_JOB_ID": 47500, "USER_ID": "BENGUI"})
    assert details["email"] == "non envoyé (pas de SMTP)"


def test_ok_du_bon_de_commande_repond_tout_de_suite(client, ifs, monkeypatch):
    lances = []
    monkeypatch.setattr(impression._fond, "submit", lambda *args: lances.append(args))
    assert client.post(OK).status_code == 200
    assert lances and lances[0][1]["RESULT_KEY_"] == "56607"


def test_numero_de_commande_et_reglages():
    assert impression.numero_de_commande(ARCHIVE_BDC) == "C105125"
    assert impression.numero_de_commande({"Notes": "N°\xa0cde: C1"}) == "C1"
    assert impression.reglages("!PDF\n$SEND_PDF=TRUE\n$SEND_PDF_TO=a@b.fr\n") == {"SEND_PDF": "TRUE",
                                                                                  "SEND_PDF_TO": "a@b.fr"}
    assert impression.imprimante_physique("ARMONY,SERVER,\\\\srv\\hp") == "\\\\srv\\hp"


def test_evenement_ecrit_comme_armony(monkeypatch):
    envoye = {}

    def requete(methode, url, **options):
        envoye.update(methode=methode, url=url, **options)
        return SimpleNamespace(ok=True, status_code=200, text="")

    monkeypatch.setattr(ecriture.requests, "request", requete)
    ecriture.EcrivainIFS(jeton="j", base="https://ifs/v1").evenement("ARMONY_REPORT_PRINT",
                                                                    {"RESULT_KEY": 1, "USER_ID": "U"})
    assert envoye["url"] == "https://ifs/v1/ReportPrintersHandling.svc/Cf_EventAction"
    assert envoye["json"] == {"Event_Lu_Name_": "FndEventAction", "Event_Id_": "ARMONY_REPORT_PRINT",
                              "Event_Data_": "$NEW:CONDITION_VALUE=RESULT_KEY=1^USER_ID=U^"}
