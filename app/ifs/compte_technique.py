"""Le compte technique : un client Keycloak en `client_credentials`, facultatif.

Pourquoi il existe : la commande se lit avec le jeton de l'utilisateur, mais une
partie de ce qu'Armony imprime vient de projections qu'un acheteur n'ouvre pas
(constaté dans le catalogue de droits de CFG, 26/10/2026) :

| Projection | Ce qu'on y lit | SVA_ACHAT | GAIFS_RF_ARMONY |
|---|---|---|---|
| CompanyHandling | SIRET, e-mails de facturation, nom du logo | – | Full |
| PersonHandling | e-mail et téléphone du coordinateur | – | Full |
| PhrasesHandling | phrases ACH04 / ACH05 | – | Full |
| PdfInsertsHandling | les CGA jointes au PDF | – | Full |
| ReportImagesHandling | le logo | – | Full |

Armony les lit avec son propre compte, porteur de `GAIFS_RF_ARMONY`. Cette
application fera de même dès qu'un client Keycloak lui sera donné, **avec un
utilisateur de service rattaché** : sans lui, IFS répond `ORA-20105
Login.FUSRNULL` (constaté par ga-commande).

Sans `IFS_TECH_CLIENT_ID`, ces lectures partent avec le jeton de l'utilisateur :
un administrateur obtient un document complet, un acheteur un document où ces
champs manquent — et `/donnees` dit lesquels.
"""

from __future__ import annotations

import os
import threading
import time

import requests

from ..config import config
from .lecture import ErreurIFS, LecteurIFS
from .sso import metadata_oidc

DELAI_S = 20
MARGE_S = 30

CLIENT_ID = os.getenv("IFS_TECH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("IFS_TECH_CLIENT_SECRET", "")

_verrou = threading.Lock()
_jeton: tuple[str, float] | None = None


def configure() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


def jeton() -> str:
    global _jeton
    with _verrou:
        if _jeton and time.time() < _jeton[1] - MARGE_S:
            return _jeton[0]
        try:
            reponse = requests.post(
                metadata_oidc()["token_endpoint"],
                data={"grant_type": "client_credentials", "client_id": CLIENT_ID,
                      "client_secret": CLIENT_SECRET},
                timeout=DELAI_S,
            )
        except requests.RequestException as err:
            raise ErreurIFS(f"Realm IFS injoignable pour le compte technique : {err}") from err
        if not reponse.ok:
            raise ErreurIFS(f"Compte technique refusé par le realm ({reponse.status_code}) : "
                            f"{reponse.text[:300]}", reponse.status_code)
        charge = reponse.json()
        _jeton = (charge["access_token"], time.time() + int(charge.get("expires_in", 300)))
        return _jeton[0]


def lecteur(langue: str) -> LecteurIFS | None:
    """Un lecteur sous l'identité technique, ou None si elle n'est pas configurée."""
    if not configure():
        return None
    return LecteurIFS(jeton=jeton(), base=config.url_projection, langue=langue)
