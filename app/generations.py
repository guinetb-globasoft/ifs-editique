"""Le journal des générations : une ligne par document demandé, avec ses temps.

Demande de Benoit (26/10/2026) : garder le temps de génération de chaque bon de
commande. Chaque demande de PDF — réussie ou non — ajoute une ligne JSON à
`data/generations.jsonl` : quand, qui, quelle commande, combien de temps en
lecture IFS et en rendu PDF, quel appel IFS a été le plus lent.

Le fichier est hors dépôt (il nomme des utilisateurs et des commandes). Il
s'ajoute ligne à ligne, sous verrou : deux générations simultanées n'y mêlent
pas leurs lignes.
"""

from __future__ import annotations

import json
import statistics
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import RACINE

FICHIER = RACINE / "data" / "generations.jsonl"
PARIS = ZoneInfo("Europe/Paris")

_verrou = threading.Lock()


def maintenant() -> str:
    return datetime.now(PARIS).isoformat(timespec="seconds")


def consigner(entree: dict[str, Any], fichier: Path | None = None) -> None:
    fichier = fichier or FICHIER
    fichier.parent.mkdir(parents=True, exist_ok=True)
    ligne = json.dumps(entree, ensure_ascii=False)
    with _verrou, fichier.open("a", encoding="utf-8") as sortie:
        sortie.write(ligne + "\n")


def lire(limite: int = 500, fichier: Path | None = None) -> list[dict[str, Any]]:
    """Les dernières générations, la plus récente d'abord."""
    fichier = fichier or FICHIER
    if not fichier.exists():
        return []
    with _verrou:
        lignes = fichier.read_text(encoding="utf-8").splitlines()
    entrees = []
    for ligne in reversed(lignes[-limite:]):
        try:
            entrees.append(json.loads(ligne))
        except ValueError:
            continue  # une ligne tronquée (arrêt brutal) ne doit pas masquer les autres
    return entrees


def statistiques(entrees: list[dict[str, Any]]) -> dict[str, Any]:
    """Nombre, médiane, moyenne et maximum du temps total des générations réussies."""
    durees = [e["duree_totale_s"] for e in entrees if e.get("statut") == "ok"]
    if not durees:
        return {"reussies": 0}
    return {
        "reussies": len(durees),
        "mediane_s": round(statistics.median(durees), 2),
        "moyenne_s": round(statistics.fmean(durees), 2),
        "max_s": round(max(durees), 2),
    }
