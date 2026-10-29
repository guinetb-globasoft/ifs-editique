"""Produire un bon de commande sans IFS, depuis des réponses enregistrées.

    .venv\\Scripts\\python.exe outils\\apercu.py                         # exemples/commande_C106553.json
    .venv\\Scripts\\python.exe outils\\apercu.py exemples\\autre.json C1   # autre jeu, autre n°
    .venv\\Scripts\\python.exe outils\\apercu.py --html                  # le HTML seul, pour régler la mise en page

Sortie dans `sorties/` (hors dépôt). Le moyen le plus court de voir l'effet d'une
retouche du gabarit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app.editiques.commande_achat import generer, lire_commande, rendre_html  # noqa: E402
from app.ifs.enregistre import LecteurEnregistre  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parametres = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parametres.add_argument("jeu", nargs="?", default=str(RACINE / "exemples" / "commande_C106553.json"))
    parametres.add_argument("numero", nargs="?", default="C106553")
    parametres.add_argument("--html", action="store_true", help="écrire le HTML au lieu du PDF")
    args = parametres.parse_args()

    lecteur = LecteurEnregistre.depuis_fichier(Path(args.jeu))
    sorties = RACINE / "sorties"
    sorties.mkdir(exist_ok=True)

    if args.html:
        document = rendre_html(lire_commande(lecteur, lecteur, args.numero))
        cible = sorties / f"Commande_{args.numero}.html"
        cible.write_text(document.corps, encoding="utf-8")
    else:
        generation = generer(lecteur, lecteur, args.numero)
        contenu, commande = generation.contenu, generation.commande
        cible = sorties / f"Commande_{args.numero}.pdf"
        cible.write_bytes(contenu)
        for avertissement in commande.avertissements:
            print("⚠", avertissement)
        print(json.dumps({"lignes": len(commande.lignes), "annexes": [a.nom for a in commande.annexes],
                          "lecture_s": generation.duree_lecture_s, "pdf_s": generation.duree_pdf_s},
                         ensure_ascii=False))
    print(cible)


if __name__ == "__main__":
    main()
