"""Lecture des projections IFS Cloud, sous l'identité de l'utilisateur.

**Lecture seule.** Ce module n'a pas de méthode d'écriture : une éditique lit
IFS, elle ne le modifie pas. Ce n'est pas un garde-fou qu'on pourrait lever,
c'est une capacité absente.

**L'identité est celle de l'utilisateur** qui a cliqué sur le bouton : son jeton
IFS est présenté tel quel. Sur IFS, un compte de service n'a pas d'identité et ne
lit rien (`ORA-20105 Login.FUSRNULL`, constaté par ga-commande et mcp-ifs) ; et
avec le jeton de l'utilisateur, ce qu'il ne voit pas à l'écran, l'éditique ne le
voit pas non plus.

Chaque appel est consigné (méthode, chemin, statut, durée — jamais le jeton) :
`/commande-achat/{n°}/donnees` les montre, et c'est par là qu'on diagnostique
une source qui manque.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote, urlencode

import requests

from ..config import config

DELAI_S = 30


class ErreurIFS(RuntimeError):
    """Un appel IFS a échoué ; `statut` vaut None si IFS n'a pas répondu."""

    def __init__(self, message: str, statut: int | None = None):
        super().__init__(message)
        self.statut = statut


@dataclass
class Appel:
    chemin: str
    statut: int | None
    duree_ms: int
    erreur: str | None = None

    def en_dict(self) -> dict[str, Any]:
        return {"chemin": self.chemin, "statut": self.statut, "duree_ms": self.duree_ms,
                "erreur": self.erreur}


class Lecteur(Protocol):
    """Ce dont une éditique a besoin pour lire IFS — et rien de plus.

    Les tests et l'aperçu hors ligne fournissent un lecteur qui sert des réponses
    enregistrées ; l'application, un `LecteurIFS`.
    """

    journal: list[Appel]

    def lire(self, chemin: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]: ...

    def lire_un(self, chemin: str, params: dict[str, str] | None = None) -> dict[str, Any]: ...

    def lire_binaire(self, chemin: str) -> bytes: ...


def litteral(valeur: str) -> str:
    """Une chaîne OData entre apostrophes, apostrophes internes doublées."""
    return "'" + str(valeur).replace("'", "''") + "'"


@dataclass
class LecteurIFS:
    jeton: str = field(repr=False)
    base: str = ""
    langue: str = "fr-FR"
    journal: list[Appel] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base = (self.base or config.url_projection).rstrip("/")

    def _get(self, chemin: str, params: dict[str, str] | None, accept: str) -> requests.Response:
        url = chemin if chemin.startswith("http") else f"{self.base}/{chemin.lstrip('/')}"
        if params:
            # IFS refuse une espace encodée « + » (ce que fait `requests` avec `params=`) : 400
            # « Demande mal formée ». `%20` passe (constaté sur CFG le 29/10/2026).
            url += ("&" if "?" in url else "?") + urlencode(params, quote_via=quote, safe="$")
        entetes = {
            "Authorization": f"Bearer {self.jeton}",
            "Accept": accept,
            # Sans elle, IFS rend les libellés traduits en anglais
            # (constaté par tests-automatisés-IFS le 26/10/2026).
            "Accept-Language": self.langue,
        }
        debut = time.monotonic()
        try:
            reponse = requests.get(url, headers=entetes, timeout=DELAI_S)
        except requests.RequestException as err:
            self._noter(chemin, params, None, debut, str(err))
            raise ErreurIFS(f"IFS injoignable ({chemin}) : {err}") from err
        if not reponse.ok:
            message = _message_ifs(reponse)
            self._noter(chemin, params, reponse.status_code, debut, message)
            raise ErreurIFS(f"{chemin} : {reponse.status_code} {message}", reponse.status_code)
        self._noter(chemin, params, reponse.status_code, debut)
        return reponse

    def _noter(self, chemin: str, params: dict[str, str] | None, statut: int | None,
               debut: float, erreur: str | None = None) -> None:
        cible = chemin + (f"?{'&'.join(f'{k}={v}' for k, v in params.items())}" if params else "")
        self.journal.append(Appel(cible, statut, int((time.monotonic() - debut) * 1000), erreur))

    def lire(self, chemin: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        """Toutes les lignes d'une collection, pages suivantes comprises.

        ⚠️ Jamais de `$top` pour lire une collection entière : IFS tronque sans
        page suivante (constaté par tests-automatisés-IFS).
        """
        lignes: list[dict[str, Any]] = []
        suivante: str | None = chemin
        while suivante:
            charge = self._get(suivante, params, "application/json").json()
            lignes.extend(charge.get("value", []))
            suivante, params = charge.get("@odata.nextLink"), None
        return lignes

    def lire_un(self, chemin: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        return self._get(chemin, params, "application/json").json()

    def lire_binaire(self, chemin: str) -> bytes:
        return self._get(chemin, None, "*/*").content


def _message_ifs(reponse: requests.Response) -> str:
    """Le message d'erreur d'IFS, tel qu'il l'a écrit, sinon le début du corps."""
    try:
        erreur = reponse.json().get("error", {})
        return f"{erreur.get('code', '')} {erreur.get('message', '')}".strip()
    except ValueError:
        return reponse.text[:300]
