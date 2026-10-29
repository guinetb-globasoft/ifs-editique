"""Écritures dans IFS : **seulement celles qu'Armony fait** quand IFS lui confie une impression (D-008).

| Écriture | Appel | Quand (connecteur Armony `ReportOk.axdata`, spec § 5.3) |
|---|---|---|
| Remplacer le PDF archivé | `PATCH PrintDialog.svc/PdfArchiveSet(ResultKey,Id)/Pdf`, `If-Match` | aperçu et OK |
| Supprimer le travail d'impression reçu | `DELETE ReportArchive.svc/PrintJobSet(PrintJobId)`, `If-Match` | OK |
| Lever un événement Armony d'IFS | `POST ReportPrintersHandling.svc/Cf_EventAction` | OK : `ARMONY_REPORT_JOB`, `ARMONY_REPORT_PRINT` |

Rien d'autre : pas de méthode générique. Une nouvelle écriture s'ajoute ici, nommée, avec la ligne d'Armony qu'elle
reproduit. L'identité est le compte technique (le client d'Armony, `ARMONY_SVC`, sur CFG) : c'est IFS qui appelle,
sans utilisateur derrière.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

from ..config import config
from .lecture import Appel, ErreurIFS, litteral

DELAI_S = 120


@dataclass
class EcrivainIFS:
    jeton: str = field(repr=False)
    base: str = ""
    journal: list[Appel] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base = (self.base or config.url_projection).rstrip("/")

    def _envoyer(self, methode: str, chemin: str, **options) -> requests.Response:
        entetes = {"Authorization": f"Bearer {self.jeton}", "Accept": "application/json",
                   "Accept-Language": "fr-FR", **options.pop("entetes", {})}
        debut = time.monotonic()
        try:
            reponse = requests.request(methode, f"{self.base}/{chemin}", headers=entetes, timeout=DELAI_S,
                                       **options)
        except requests.RequestException as err:
            self.journal.append(Appel(f"{methode} {chemin}", None, int((time.monotonic() - debut) * 1000), str(err)))
            raise ErreurIFS(f"IFS injoignable ({methode} {chemin}) : {err}") from err
        erreur = None if reponse.ok else reponse.text[:300]
        self.journal.append(Appel(f"{methode} {chemin}", reponse.status_code,
                                  int((time.monotonic() - debut) * 1000), erreur))
        if not reponse.ok:
            raise ErreurIFS(f"{methode} {chemin} : {reponse.status_code} {erreur}", reponse.status_code)
        return reponse

    def remplacer_pdf(self, cle: int, id_pdf: str, etag: str, contenu: bytes) -> None:
        self._envoyer("PATCH", f"PrintDialog.svc/PdfArchiveSet(ResultKey={cle},Id={litteral(id_pdf)})/Pdf",
                      data=contenu, entetes={"If-Match": etag, "Content-Type": "application/octet-stream"})

    def supprimer_travail(self, travail: int, etag: str) -> None:
        self._envoyer("DELETE", f"ReportArchive.svc/PrintJobSet(PrintJobId={travail})", entetes={"If-Match": etag})

    def evenement(self, evenement: str, valeurs: dict[str, object]) -> None:
        """Un événement personnalisé d'IFS, sous la forme exacte qu'utilise Armony :
        `$NEW:CONDITION_VALUE=CLE=valeur^CLE=valeur^`."""
        donnees = "$NEW:CONDITION_VALUE=" + "".join(f"{k}={v}^" for k, v in valeurs.items())
        self._envoyer("POST", "ReportPrintersHandling.svc/Cf_EventAction", json={
            "Event_Lu_Name_": "FndEventAction", "Event_Id_": evenement, "Event_Data_": donnees})
