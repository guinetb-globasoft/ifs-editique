"""Le point d'entrée d'IFS à l'impression : les mêmes adresses qu'Armony (D-008, spec § 5.2).

IFS appelle `{ARMONY_SERVER}/GetDownload.aspx` pour l'aperçu (synchrone : la boîte attend) et
`{ARMONY_SERVER}/Execute.aspx` pour OK et l'agent Aurena (asynchrones). Pointer le paramètre système
`ARMONY_SERVER` vers l'application suffit à la brancher ; lui rendre sa valeur la débranche. Ce paramètre vaut pour
toutes les éditiques : ce qui n'est pas le bon de commande est **relayé tel quel** au serveur Armony
(`ARMONY_RELAIS`).

    GET  /GetDownload.aspx?layout_name=ReportPreview.axdata&RESULT_KEY_=…&PRINT_JOB_ID_=…&USER_ID_=…
    POST /Execute.aspx?layout_name=ReportOk.axdata&AxAsync=True&RESULT_KEY_=…&PRINT_JOB_ID_=…&USER_ID_=…
         &LANGUAGE_CODE_=…&LAYOUT_NAME_=…&LOCALE_LANGUAGE_=…&LOCALE_COUNTRY_=…&COPIES_=…
    POST /Execute.aspx?layout_name=ReportAurenaAgent.axdata&PRINT_JOB_ID_=…     -> toujours relayé

IFS n'envoie aucune authentification (comme vers Armony) : tout est lu et écrit avec le compte technique.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation

import requests
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, Response

from . import generations
from .config import config
from .editiques import commande_achat
from .ifs import compte_technique
from .ifs.ecriture import EcrivainIFS
from .ifs.lecture import ErreurIFS, LecteurIFS
from .version import VERSION

journal = logging.getLogger("uvicorn.error")
routeur = APIRouter()

RAPPORT = "PURCHASE_ORDER_PRINT_REP"
DISPOSITION = "PurchaseOrderPrintRepArmony.rdl"
APERCU, OK, AGENT = "ReportPreview.axdata", "ReportOk.axdata", "ReportAurenaAgent.axdata"
# La boîte d'aperçu abandonne vers 60 s (constat INT-281, ga-talend) : on ne l'attend pas au-delà.
ATTENTE_ARCHIVE_S = 45
# ARMONY_REPORT_JOB attend lui-même jusqu'à 30 s que son travail soit exécuté.
ATTENTE_TRAVAIL_S = 60
ESSAIS_EVENEMENT = 3

_fond = ThreadPoolExecutor(max_workers=2, thread_name_prefix="impression-ok")


class NonTraite(Exception):
    """Ce n'est pas un bon de commande « Armony layout » : relayer à Armony."""


def _relais() -> str:
    return config.armony_relais


def _technique() -> tuple[LecteurIFS, EcrivainIFS]:
    if not compte_technique.configure():
        raise ErreurIFS("Compte technique non configuré (IFS_TECH_CLIENT_ID / IFS_TECH_CLIENT_SECRET).")
    jeton = compte_technique.jeton()
    return (LecteurIFS(jeton=jeton, base=config.url_projection, langue="fr-FR"),
            EcrivainIFS(jeton=jeton, base=config.url_projection))


def entier(valeur: str) -> int:
    """Une clé passée par IFS dans l'URL. Il l'écrit en décimal : `RESULT_KEY_=56608.0` (constaté sur CFG le
    29/10/2026, premier appel réel)."""
    return int(Decimal(valeur))


def numero_de_commande(rapport: dict | None) -> str | None:
    """Le n° de commande d'une impression archivée : `PDF_EVENT_PARAM_6` des paramètres (archive 56607 de CFG,
    29/10/2026 ; l'action standard « Purchase Order email » l'emploie ainsi), sinon la note « N° cde: … »."""
    rapport = rapport or {}
    trouve = (re.search(r"\$PDF_EVENT_PARAM_6=([^\r\n]+)", rapport.get("EventParams") or "")
              or re.search(r"cde\s*:\s*(\S+)", rapport.get("Notes") or ""))
    return trouve.group(1).strip() if trouve else None


def reglages(texte: str | None) -> dict[str, str]:
    """Les réglages d'un travail d'impression (`Settings`, message IFS `!…\\n$CLE=valeur\\n`), comme Armony les
    découpe : une ligne par réglage, `$` retiré."""
    valeurs: dict[str, str] = {}
    for ligne in (texte or "").splitlines():
        if "=" in ligne and not ligne.startswith("!"):
            cle, valeur = ligne.split("=", 1)
            valeurs[cle.lstrip("$").strip()] = valeur.strip()
    return valeurs


def _rapport(lecteur: LecteurIFS, cle: int) -> dict | None:
    lignes = lecteur.lire("ReportArchive.svc/ArchiveSet", {"$filter": f"ResultKey eq {cle}"})
    return lignes[0] if lignes else None


def _bon_de_commande(lecteur: LecteurIFS, cle: int) -> tuple[dict, str]:
    rapport = _rapport(lecteur, cle)
    if not rapport or rapport.get("ReportId") != RAPPORT:
        raise NonTraite(f"rapport {(rapport or {}).get('ReportId')}")
    numero = numero_de_commande(rapport)
    if not numero:
        raise ErreurIFS(f"N° de commande introuvable dans l'archive {cle}.")
    return rapport, numero


def _attendre_pdf(lecteur: LecteurIFS, cle: int, travail: int) -> dict:
    """La ligne PdfArchive du travail, dès qu'IFS y a déposé sa page d'attente « Armony Report »."""
    fin = time.monotonic() + ATTENTE_ARCHIVE_S
    while True:
        lignes = lecteur.lire("PrintDialog.svc/PdfArchiveSet",
                              {"$filter": f"ResultKey eq {cle} and PrintJobId eq {travail}"})
        if lignes:
            return lignes[-1]
        if time.monotonic() > fin:
            raise ErreurIFS(f"Aucun PDF archivé pour la clé {cle}, travail {travail}, après {ATTENTE_ARCHIVE_S} s.")
        time.sleep(0.5)


def _deposer(lecteur: LecteurIFS, ecrivain: EcrivainIFS, cle: int, travail: int, contenu: bytes) -> None:
    """Remplace le PDF archivé du travail ; relit la ligne et réessaie une fois si IFS l'a modifiée entre-temps."""
    ligne = _attendre_pdf(lecteur, cle, travail)
    try:
        ecrivain.remplacer_pdf(cle, ligne["Id"], ligne["@odata.etag"], contenu)
    except ErreurIFS as err:
        if err.statut != 412:
            raise
        ligne = _attendre_pdf(lecteur, cle, travail)
        ecrivain.remplacer_pdf(cle, ligne["Id"], ligne["@odata.etag"], contenu)


def _generer(lecteur: LecteurIFS, numero: str):
    return commande_achat.generer(lecteur, lecteur, numero, config.langue)


def apercu(cle: int, travail: int) -> dict:
    """Prévisualisation : notre PDF à la place de la page d'attente, avant que la boîte ne l'affiche."""
    lecteur, ecrivain = _technique()
    _, numero = _bon_de_commande(lecteur, cle)
    # La génération part tout de suite ; IFS archive sa page d'attente en ~2 s (INT-281), bien avant qu'on écrive.
    generation = _generer(lecteur, numero)
    _deposer(lecteur, ecrivain, cle, travail, generation.contenu)
    return {"numero": numero, "pages": generation.pages, "duree_lecture_ifs_s": generation.duree_lecture_s,
            "duree_pdf_s": generation.duree_pdf_s, "avertissements": len(generation.commande.avertissements)}


def _evenement(ecrivain: EcrivainIFS, evenement: str, valeurs: dict[str, object]) -> None:
    """Comme Armony, qui réessaie `Cf_EventAction` jusqu'à 20 fois : ici 3, avec une seconde d'écart."""
    for essai in range(ESSAIS_EVENEMENT):
        try:
            return ecrivain.evenement(evenement, valeurs)
        except ErreurIFS:
            if essai == ESSAIS_EVENEMENT - 1:
                raise
            time.sleep(1)


def _attendre_travail(lecteur: LecteurIFS, cle: int, guid: str) -> int:
    fin = time.monotonic() + ATTENTE_TRAVAIL_S
    while True:
        lignes = lecteur.lire("ReportArchive.svc/PrintJobSet",
                              {"$filter": f"ResultKey eq {cle} and Message eq '{guid}'"})
        if lignes:
            return int(lignes[0]["PrintJobId"])
        if time.monotonic() > fin:
            raise ErreurIFS(f"Le travail créé par ARMONY_REPORT_JOB ({guid}) n'est pas apparu après "
                            f"{ATTENTE_TRAVAIL_S} s.")
        time.sleep(1)


def imprimante_physique(imprimante: str) -> str:
    """Ce qu'Armony renvoie dans ARMONY_REPORT_PRINT : la partie après « ,SERVER, » de l'imprimante IFS.
    Sans ce motif, on la renvoie entière (le calcul d'Armony en retranche alors 7 caractères : non reproduit)."""
    return imprimante.split(",SERVER,", 1)[1] if ",SERVER," in imprimante else imprimante


def ok(parametres: dict[str, str]) -> dict:
    """OK dans la boîte : la suite exacte du connecteur Armony `ReportOk.axdata` (spec § 5.3)."""
    lecteur, ecrivain = _technique()
    cle, travail = entier(parametres["RESULT_KEY_"]), entier(parametres["PRINT_JOB_ID_"])
    _, numero = _bon_de_commande(lecteur, cle)

    # 1. Le travail reçu : son imprimante, ses réglages (adresse e-mail…), puis sa suppression.
    recus = lecteur.lire("ReportArchive.svc/PrintJobSet", {"$filter": f"PrintJobId eq {travail}"})
    if not recus:
        raise ErreurIFS(f"Travail d'impression {travail} introuvable.")
    recu = recus[0]
    imprimante, valeurs = recu.get("PrinterId") or "", reglages(recu.get("Settings"))
    ecrivain.supprimer_travail(travail, recu["@odata.etag"])

    # 2. Un travail à nous, NO_PRINTOUT et sans e-mail d'IFS, retrouvé par son GUID.
    guid = str(uuid.uuid4())
    _evenement(ecrivain, "ARMONY_REPORT_JOB", {
        "PRINTER_ID": imprimante, "RESULT_KEY": cle, "LAYOUT_NAME": parametres.get("LAYOUT_NAME_", ""),
        "LANGUAGE_CODE": parametres.get("LANGUAGE_CODE_", ""),
        "LOCALE_LANGUAGE": parametres.get("LOCALE_LANGUAGE_", ""),
        "LOCALE_COUNTRY": parametres.get("LOCALE_COUNTRY_", ""), "PRINT_JOB_GUID": guid})
    nouveau = _attendre_travail(lecteur, cle, guid)

    # 3. Notre PDF dans l'archive de ce travail.
    generation = _generer(lecteur, numero)
    _deposer(lecteur, ecrivain, cle, nouveau, generation.contenu)

    # 4. L'e-mail : pas encore de serveur SMTP (spec Q13). On le dit, on ne l'invente pas.
    destinataire = valeurs.get("SEND_PDF_TO") or valeurs.get("PDF_EVENT_PARAM_1")
    if destinataire:
        journal.warning("Impression %s (%s) : e-mail à %s NON envoyé, pas de serveur SMTP configuré.",
                        cle, numero, destinataire)

    # 5. L'archive passe « imprimée ».
    _evenement(ecrivain, "ARMONY_REPORT_PRINT", {
        "PRINTER_ID": imprimante_physique(imprimante), "RESULT_KEY": cle, "PRINT_JOB_ID": nouveau,
        "USER_ID": parametres.get("USER_ID_", "")})
    return {"numero": numero, "travail_cree": nouveau, "pages": generation.pages,
            "duree_lecture_ifs_s": generation.duree_lecture_s, "duree_pdf_s": generation.duree_pdf_s,
            "avertissements": len(generation.commande.avertissements),
            "email": "non envoyé (pas de SMTP)" if destinataire else "aucune adresse"}


def _consigner(geste: str, parametres: dict[str, str], debut: float, statut: str, **details) -> None:
    entree = {"horodatage": generations.maintenant(), "editique": "commande-achat", "source": "impression-ifs",
              "geste": geste, "cle": parametres.get("RESULT_KEY_"), "travail": parametres.get("PRINT_JOB_ID_"),
              "utilisateur": parametres.get("USER_ID_"), "instance_ifs": config.instance_ifs, "version": VERSION,
              "statut": statut, "duree_totale_s": round(time.monotonic() - debut, 3), **details}
    generations.consigner(entree)
    journal.info("Impression IFS %s, clé %s : %s en %.1f s %s", geste, entree["cle"], statut,
                 entree["duree_totale_s"], {k: v for k, v in details.items() if v is not None})


def _relayer(chemin: str, methode: str, requete: str, corps: bytes, type_contenu: str | None) -> Response:
    if not _relais():
        return PlainTextResponse("Relais Armony non configuré (ARMONY_RELAIS).", status_code=502)
    url = f"{_relais()}/{chemin}" + (f"?{requete}" if requete else "")
    try:
        reponse = requests.request(methode, url, data=corps or None, timeout=180,
                                   headers={"Content-Type": type_contenu} if corps and type_contenu else {})
    except requests.RequestException as err:
        journal.error("Relais Armony injoignable (%s) : %s", url, err)
        return PlainTextResponse(f"Relais Armony injoignable : {err}", status_code=502)
    return Response(reponse.content, status_code=reponse.status_code,
                    media_type=reponse.headers.get("content-type"))


@routeur.api_route("/GetDownload.aspx", methods=["GET", "POST"])
async def get_download(request: Request):
    parametres, debut = dict(request.query_params), time.monotonic()
    corps = await request.body()
    if parametres.get("layout_name") != APERCU:
        return await run_in_threadpool(_relayer, "GetDownload.aspx", request.method, request.url.query, corps,
                                       request.headers.get("content-type"))
    try:
        details = await run_in_threadpool(apercu, entier(parametres["RESULT_KEY_"]),
                                          entier(parametres["PRINT_JOB_ID_"]))
    except NonTraite as raison:
        journal.info("Aperçu clé %s relayé à Armony (%s).", parametres.get("RESULT_KEY_"), raison)
        return await run_in_threadpool(_relayer, "GetDownload.aspx", request.method, request.url.query, corps,
                                       request.headers.get("content-type"))
    except (ErreurIFS, KeyError, ValueError, InvalidOperation) as err:
        _consigner("apercu", parametres, debut, "erreur", erreur=str(err))
        return PlainTextResponse(f"Éditique non produite : {err}", status_code=500)
    _consigner("apercu", parametres, debut, "ok", **details)
    return PlainTextResponse("OK")


def _ok_en_fond(parametres: dict[str, str], corps: bytes, type_contenu: str | None, requete: str) -> None:
    debut = time.monotonic()
    try:
        details = ok(parametres)
    except NonTraite as raison:
        journal.info("OK clé %s relayé à Armony (%s).", parametres.get("RESULT_KEY_"), raison)
        _relayer("Execute.aspx", "POST", requete, corps, type_contenu)
        return
    except Exception as err:  # en tâche de fond, rien ne doit se perdre sans trace
        _consigner("ok", parametres, debut, "erreur", erreur=str(err))
        journal.exception("Impression IFS (OK) clé %s en échec", parametres.get("RESULT_KEY_"))
        return
    _consigner("ok", parametres, debut, "ok", **details)


@routeur.api_route("/Execute.aspx", methods=["GET", "POST"])
async def execute(request: Request):
    parametres = dict(request.query_params)
    corps = await request.body()
    type_contenu = request.headers.get("content-type")
    if parametres.get("layout_name") == OK and parametres.get("LAYOUT_NAME_") == DISPOSITION:
        # Asynchrone, comme Armony (AxAsync=True) : IFS n'attend pas la fin du traitement.
        _fond.submit(_ok_en_fond, parametres, corps, type_contenu, request.url.query)
        return PlainTextResponse("OK")
    return await run_in_threadpool(_relayer, "Execute.aspx", request.method, request.url.query, corps, type_contenu)
