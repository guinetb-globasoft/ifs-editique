"""Éditique « Commande d'achat », reprise du projet Armony `Commande_dachat v1`.

    donnees.py       IFS -> CommandeAchat (ce que le document affiche, non formaté)
    modele.py        la forme de CommandeAchat
    mise_en_page.py  CommandeAchat -> HTML, en-tête, pied
    gabarit/         la mise en page (Jinja2 + CSS), et ses libellés
    __init__.py      generer() : du numéro de commande au PDF final, chronométré
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ...ifs.lecture import Lecteur
from ...rendu import pdf
from ...version import VERSION
from .donnees import lire_commande
from .mise_en_page import rendre_html
from .modele import CommandeAchat

__all__ = ["generer", "lire_commande", "rendre_html", "CommandeAchat", "Generation"]


@dataclass
class Generation:
    contenu: bytes = field(repr=False)
    commande: CommandeAchat
    pages: int
    duree_lecture_s: float
    duree_pdf_s: float


def generer(utilisateur: Lecteur, reference: Lecteur, numero: str, langue: str = "fr") -> Generation:
    """Le PDF de la commande — bon de commande puis CGA —, les données lues, et les temps."""
    debut = time.monotonic()
    commande = lire_commande(utilisateur, reference, numero, langue)
    lu = time.monotonic()
    document = rendre_html(commande, langue)
    principal = pdf.html_vers_pdf(document.corps, document.entete, document.pied, document.marges)
    contenu = pdf.signer(pdf.concatener(principal, [a.contenu for a in commande.annexes]),
                         f"Bon de commande {numero}", f"ifs-app-editique {VERSION}")
    return Generation(contenu, commande, pdf.nombre_de_pages(principal),
                      round(lu - debut, 3), round(time.monotonic() - lu, 3))
