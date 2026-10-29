"""CommandeAchat -> HTML du corps, de l'en-tête et du pied de page Chromium."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ...rendu.formats import date_fr, montant_euros, nombre
from ...version import VERSION
from .modele import CommandeAchat

GABARIT = Path(__file__).resolve().parent / "gabarit"

# Marges de page, en mm. Le haut abrite le logo, le bas le pied de page et le
# numéro « n/N » : ce sont les zones « Container » d'Armony, répétées à chaque page.
# Le texte coule jusqu'à 282,2 mm : c'est là que s'arrête la dernière ligne
# d'Armony quand la page 1 est pleine, au ras du pied de page.
MARGES = {"top": "25mm", "bottom": "14.8mm", "left": "0mm", "right": "0mm"}

_env = Environment(loader=FileSystemLoader(GABARIT), undefined=StrictUndefined,
                   autoescape=True, trim_blocks=True, lstrip_blocks=True)
_env.filters.update(nombre=nombre, euros=montant_euros, date_fr=date_fr)


@dataclass
class Document:
    corps: str
    entete: str
    pied: str
    marges: dict[str, str]


def libelles(langue: str) -> dict[str, str]:
    """Code Armony -> libellé ; repli sur le français, puis sur le code lui-même."""
    table = json.loads((GABARIT / "libelles.json").read_text(encoding="utf-8"))["libelles"]
    return {code: textes.get(langue) or textes.get("fr") or code for code, textes in table.items()}


def rendre_html(commande: CommandeAchat, langue: str = "fr") -> Document:
    t = libelles(langue)
    logo = (f"data:{commande.logo_type};base64,{base64.b64encode(commande.logo).decode()}"
            if commande.logo else "")
    contexte = {"c": commande, "t": lambda code: t.get(code, code), "logo": logo,
                "version": VERSION, "style": (GABARIT / "style.css").read_text(encoding="utf-8")}
    return Document(
        corps=_env.get_template("document.html.j2").render(contexte),
        entete=_env.get_template("entete.html.j2").render(contexte),
        pied=_env.get_template("pied.html.j2").render(contexte),
        marges=MARGES,
    )
