"""Login IFS de l'utilisateur : OIDC *authorization code* + PKCE sur le realm IFS.

Le parcours voulu : l'utilisateur clique sur le bouton dans IFS, un onglet
s'ouvre sur `/commande-achat/<n°>`, l'application le renvoie au realm IFS —
**où il est déjà connecté**, donc sans rien saisir — puis reprend la commande
avec son jeton. Pour l'utilisateur, c'est un clic.

Un appelant qui n'est pas un navigateur (autre application, test) présente son
propre jeton IFS dans `Authorization: Bearer …` : il est relayé tel quel, sans
session.

Les jetons vivent **en mémoire du processus**, indexés par l'identifiant de
session porté par le cookie signé — jamais dans le cookie lui-même. Un
redémarrage renvoie au realm, ce qui, pour un utilisateur déjà connecté à IFS,
ne lui coûte rien.

Le rafraîchissement se fait **sous verrou, par session** : Keycloak fait tourner
les refresh tokens en usage unique et révoque la session entière si deux
rafraîchissements se croisent (leçon de ga-commande, ADR-009).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import config

DELAI_S = 20
MARGE_S = 30
DUREE_CACHE_OIDC_S = 3600

routeur = APIRouter()
# Le logger d'uvicorn : ses messages sortent dans la console du serveur sans réglage.
journal = logging.getLogger("uvicorn.error")


class ErreurSSO(RuntimeError):
    """Le realm a refusé, ou la configuration est incomplète."""


# --------------------------------------------------------------- découverte
_decouverte: dict[str, tuple[float, dict[str, Any]]] = {}


def metadata_oidc() -> dict[str, Any]:
    """Les endpoints publiés par le realm, jamais écrits en dur (cache d'une heure)."""
    issuer = config.issuer
    entree = _decouverte.get(issuer)
    if entree and time.time() - entree[0] < DUREE_CACHE_OIDC_S:
        return entree[1]
    url = f"{issuer}/.well-known/openid-configuration"
    try:
        reponse = requests.get(url, timeout=DELAI_S)
        reponse.raise_for_status()
        metadata = reponse.json()
    except (requests.RequestException, ValueError) as err:
        raise ErreurSSO(f"Découverte OIDC impossible sur {url} : {err}") from err
    _decouverte[issuer] = (time.time(), metadata)
    return metadata


# ------------------------------------------------------------------- jetons
@dataclass
class Jeton:
    access_token: str = field(repr=False)
    expire_a: float
    refresh_token: str = field(default="", repr=False)
    refresh_expire_a: float = 0.0
    utilisateur: str = ""
    duree: float = 0.0

    def _marge(self) -> float:
        # ⚠️ Une marge fixe de 30 s rend inutilisable, dès sa réception, un jeton
        # qui vit 30 s ou moins : l'application repartait au realm, qui renvoyait
        # aussitôt, en boucle (constaté le 26/10/2026). La marge suit la durée.
        return min(MARGE_S, self.duree / 4) if self.duree else MARGE_S

    def utilisable(self) -> bool:
        return time.time() < self.expire_a - self._marge()

    def rafraichissable(self) -> bool:
        return bool(self.refresh_token) and time.time() < self.refresh_expire_a - self._marge()


_jetons: dict[str, Jeton] = {}
_verrous: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def _depuis_reponse(charge: dict[str, Any]) -> Jeton:
    maintenant = time.time()
    duree = int(charge.get("expires_in", 180))
    return Jeton(
        access_token=charge["access_token"],
        expire_a=maintenant + duree,
        refresh_token=charge.get("refresh_token", ""),
        refresh_expire_a=maintenant + int(charge.get("refresh_expires_in", 0)),
        utilisateur=utilisateur_du_jeton(charge["access_token"]),
        duree=duree,
    )


def decrire(charge: dict[str, Any]) -> str:
    """Ce que le realm a rendu, sans aucun jeton : pour la console et la page d'erreur."""
    return (f"jeton de {utilisateur_du_jeton(charge.get('access_token', '')) or '?'} "
            f"valable {charge.get('expires_in', '?')} s, "
            f"refresh token {'présent' if charge.get('refresh_token') else 'absent'} "
            f"(valable {charge.get('refresh_expires_in', '?')} s), client {config.ifs_client_id}")


def utilisateur_du_jeton(jeton: str) -> str:
    """L'identifiant IFS lu dans le jeton, **pour l'affichage seulement**.

    La signature n'est pas vérifiée ici : c'est IFS qui la vérifie à chaque
    appel, et rien n'est décidé sur la foi de ce nom.
    """
    try:
        charge = jeton.split(".")[1]
        donnees = json.loads(base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4)))
    except (IndexError, ValueError):
        return ""
    return str(donnees.get("preferred_username") or donnees.get("sub") or "").upper()


def _appeler_token(donnees: dict[str, str]) -> dict[str, Any]:
    url = metadata_oidc()["token_endpoint"]
    donnees = {**donnees, "client_id": config.ifs_client_id,
               "client_secret": config.ifs_client_secret}
    try:
        reponse = requests.post(url, data=donnees, timeout=DELAI_S)
    except requests.RequestException as err:
        raise ErreurSSO(f"Realm IFS injoignable : {err}") from err
    if not reponse.ok:
        raise ErreurSSO(f"Le realm IFS a refusé ({reponse.status_code}) : {reponse.text[:300]}")
    return reponse.json()


def jeton_de_session(sid: str | None) -> Jeton | None:
    """Le jeton de la session, rafraîchi si besoin ; None s'il faut repasser au realm."""
    if not sid:
        return None
    jeton = _jetons.get(sid)
    if jeton is None or jeton.utilisable():
        return jeton
    with _verrous[sid]:
        # Second contrôle : une autre requête de la même session a pu rafraîchir
        # pendant qu'on attendait le verrou.
        jeton = _jetons.get(sid)
        if jeton is None or jeton.utilisable():
            return jeton
        if not jeton.rafraichissable():
            _jetons.pop(sid, None)
            return None
        try:
            charge = _appeler_token({"grant_type": "refresh_token",
                                     "refresh_token": jeton.refresh_token})
        except ErreurSSO:
            _jetons.pop(sid, None)
            return None
        _jetons[sid] = _depuis_reponse(charge)
        return _jetons[sid]


def jeton_de_la_requete(request: Request) -> str | None:
    """Le jeton IFS à présenter pour cette requête, ou None.

    `Authorization: Bearer` d'abord — l'appelant parle pour lui-même —, puis la
    session du navigateur.
    """
    entete = request.headers.get("authorization", "")
    if entete.lower().startswith("bearer "):
        return entete[7:].strip() or None
    jeton = jeton_de_session(request.session.get("sid"))
    return jeton.access_token if jeton else None


def retour_sur(chemin: str | None) -> str:
    """Un chemin de retour interne, jamais une URL : pas de redirection ouverte."""
    if chemin and chemin.startswith("/") and not chemin.startswith("//"):
        return chemin
    return "/"


# ------------------------------------------------------------------- routes
@routeur.get("/auth/ifs/login")
def login(request: Request, retour: str = "/"):
    incomplet = config.pourquoi_sso_incomplet()
    if incomplet:
        return HTMLResponse(f"<p>Login IFS impossible : {incomplet}</p>", status_code=500)
    verificateur = secrets.token_urlsafe(64)
    defi = base64.urlsafe_b64encode(hashlib.sha256(verificateur.encode()).digest()).rstrip(b"=")
    etat = secrets.token_urlsafe(24)
    request.session["oidc"] = {"etat": etat, "verificateur": verificateur,
                               "retour": retour_sur(retour)}
    parametres = {
        "response_type": "code",
        "client_id": config.ifs_client_id,
        "redirect_uri": config.ifs_oidc_redirect_uri,
        "scope": config.ifs_oidc_scope,
        "state": etat,
        "code_challenge": defi.decode(),
        "code_challenge_method": "S256",
    }
    return RedirectResponse(f"{metadata_oidc()['authorization_endpoint']}?{urlencode(parametres)}")


@routeur.get("/auth/ifs/callback/")
def callback(request: Request, code: str = "", state: str = "", error: str = "",
             error_description: str = ""):
    attendu = request.session.pop("oidc", None)
    if error:
        return HTMLResponse(f"<p>Le realm IFS a refusé : {error} {error_description}</p>",
                            status_code=401)
    if not attendu or not secrets.compare_digest(state, attendu["etat"]):
        # Cookie perdu en route : le plus souvent localhost d'un côté, 127.0.0.1 de l'autre.
        return HTMLResponse("<p>Retour du realm sans état de session valide. L'URL ouverte "
                            "et IFS_OIDC_REDIRECT_URI doivent avoir le même hôte.</p>",
                            status_code=400)
    try:
        charge = _appeler_token({"grant_type": "authorization_code", "code": code,
                                 "redirect_uri": config.ifs_oidc_redirect_uri,
                                 "code_verifier": attendu["verificateur"]})
    except ErreurSSO as err:
        return HTMLResponse(f"<p>{err}</p>", status_code=401)
    sid = request.session.get("sid") or secrets.token_urlsafe(24)
    request.session["sid"] = sid
    _jetons[sid] = _depuis_reponse(charge)
    # Ce qui permet à la page suivante de reconnaître une boucle et de l'expliquer.
    request.session["retour_realm"] = {"a": time.time(), "diagnostic": decrire(charge)}
    journal.info("retour du realm : %s", decrire(charge))
    return RedirectResponse(attendu["retour"])


def boucle_probable(request: Request) -> str | None:
    """Le diagnostic du dernier retour du realm s'il date de moins de 30 s, sinon None.

    Revenir du realm et n'avoir pourtant aucun jeton utilisable, c'est la boucle
    assurée : le realm, où l'utilisateur est connecté, renverrait aussitôt.
    """
    retour = request.session.get("retour_realm")
    if retour and time.time() - retour.get("a", 0) < 30:
        return retour.get("diagnostic", "")
    return None


@routeur.get("/auth/ifs/statut")
def statut(request: Request):
    """L'état de la session IFS, sans aucun jeton : à ouvrir quand le login se comporte mal."""
    jeton = _jetons.get(request.session.get("sid", ""))
    return {
        "client": config.ifs_client_id,
        "redirect_uri": config.ifs_oidc_redirect_uri,
        "session": bool(request.session.get("sid")),
        "jeton": None if jeton is None else {
            "utilisateur": jeton.utilisateur,
            "expire_dans_s": int(jeton.expire_a - time.time()),
            "utilisable": jeton.utilisable(),
            "rafraichissable": jeton.rafraichissable(),
        },
        "dernier_retour_realm": request.session.get("retour_realm"),
    }


@routeur.get("/auth/ifs/deconnexion")
def deconnexion(request: Request):
    sid = request.session.pop("sid", None)
    if sid:
        _jetons.pop(sid, None)
    return RedirectResponse("/")


def utilisateur_connecte(request: Request) -> str:
    jeton = jeton_de_session(request.session.get("sid"))
    return jeton.utilisateur if jeton else ""
