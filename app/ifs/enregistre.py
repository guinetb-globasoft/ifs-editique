"""Un lecteur qui sert des réponses IFS enregistrées : tests et aperçu hors ligne.

Fichier JSON :

    {"reponses": {"<chemin>": <corps JSON>, "<chemin>|<$filter>": <corps JSON>},
     "binaires": {"<chemin>": "<fichier relatif au JSON>"}}

Une clé `chemin|filtre` l'emporte sur la clé `chemin` seule. Un chemin absent
répond comme IFS : 404.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .lecture import Appel, ErreurIFS


@dataclass
class LecteurEnregistre:
    reponses: dict[str, Any]
    binaires: dict[str, bytes] = field(default_factory=dict)
    journal: list[Appel] = field(default_factory=list)

    @classmethod
    def depuis_fichier(cls, chemin: Path) -> "LecteurEnregistre":
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        binaires = {cle: (chemin.parent / fichier).read_bytes()
                    for cle, fichier in donnees.get("binaires", {}).items()}
        return cls(donnees["reponses"], binaires)

    def _trouver(self, chemin: str, params: dict[str, str] | None) -> Any:
        filtre = (params or {}).get("$filter")
        for cle in ((f"{chemin}|{filtre}",) if filtre else ()) + (chemin,):
            if cle in self.reponses:
                self.journal.append(Appel(cle, 200, 0))
                return self.reponses[cle]
        self.journal.append(Appel(chemin, 404, 0, "absent de l'enregistrement"))
        raise ErreurIFS(f"{chemin} : 404 absent de l'enregistrement", 404)

    def lire(self, chemin: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        return list(self._trouver(chemin, params))

    def lire_un(self, chemin: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        return dict(self._trouver(chemin, params))

    def lire_binaire(self, chemin: str) -> bytes:
        if chemin in self.binaires:
            self.journal.append(Appel(chemin, 200, 0))
            return self.binaires[chemin]
        self.journal.append(Appel(chemin, 404, 0, "absent de l'enregistrement"))
        raise ErreurIFS(f"{chemin} : 404 absent de l'enregistrement", 404)
