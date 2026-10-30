"""Mesurer notre PDF contre le PDF Armony : la position de chaque texte commun, à sa ligne de base (D-010).

    .venv\\Scripts\\python.exe outils\\mesurer_mise_en_page.py <notre.pdf> <armony.pdf> [--pages 2] [--detail 10]

Compare, page par page, les textes présents une seule fois dans chacun des deux PDF : écart vertical et horizontal
de leur **origine** (la ligne de base, là où le moteur PDF pose réellement les caractères), en millimètres.

⚠️ Ne jamais mesurer sur le haut des boîtes de texte (`bbox`) : DynamicPDF (Armony) et Chromium ne déclarent pas la
même hauteur de police. Sur cette mesure, l'écart paraissait sous 0,3 mm alors que les textes étaient en réalité
jusqu'à 0,8 mm trop haut (constaté le 29/10/2026 : le titre du bandeau affleurait le bord, « haché »).

Rend aussi la position du bandeau rose (rectangle plein de plus de 150 mm de large). Lecture seule. Demande PyMuPDF
(`requirements-dev.txt`).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict

try:
    import pymupdf
except ImportError:  # anciennes versions
    import fitz as pymupdf

MM = 25.4 / 72


def textes(chemin: str, pages: int) -> dict[tuple[int, str], tuple[float, float]]:
    """(page, texte) -> (x, y) de la ligne de base en mm, pour les textes présents une seule fois sur leur page."""
    document = pymupdf.open(chemin)
    vus: dict[tuple[int, str], list[tuple[float, float]]] = defaultdict(list)
    for i in range(min(pages, document.page_count)):
        for bloc in document[i].get_text("dict")["blocks"]:
            for ligne in bloc.get("lines", []):
                for morceau in ligne["spans"]:
                    texte = morceau["text"].strip()
                    if len(texte) >= 3:
                        vus[(i, texte)].append((morceau["origin"][0] * MM, morceau["origin"][1] * MM))
    return {cle: positions[0] for cle, positions in vus.items() if len(positions) == 1}


def bandeau(chemin: str) -> tuple[float, float] | None:
    for dessin in pymupdf.open(chemin)[0].get_drawings():
        r, fond = dessin["rect"], dessin.get("fill")
        if fond and r.width * MM > 150 and 8 < r.height * MM < 15 and fond[0] > 0.8 and fond[1] < 0.3:
            return r.y0 * MM, r.y1 * MM
    return None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parametres = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parametres.add_argument("notre")
    parametres.add_argument("armony")
    parametres.add_argument("--pages", type=int, default=2, help="pages du bon à comparer (les CGA suivent)")
    parametres.add_argument("--detail", type=int, default=10, help="nombre de plus grands écarts à lister")
    args = parametres.parse_args()

    a, n = textes(args.armony, args.pages), textes(args.notre, args.pages)
    communs = sorted(k for k in a if k in n)
    if not communs:
        sys.exit("Aucun texte commun : les deux PDF ne portent pas la même commande ?")
    dy = {k: n[k][1] - a[k][1] for k in communs}
    dx = {k: n[k][0] - a[k][0] for k in communs}
    pire = max(max(abs(v) for v in dy.values()), max(abs(v) for v in dx.values()))
    print(f"{len(communs)} textes communs sur {args.pages} page(s), mesurés à la ligne de base")
    print(f"  vertical   : médiane {statistics.median(dy.values()):+.2f} mm, max {max(abs(v) for v in dy.values()):.2f} mm")
    print(f"  horizontal : médiane {statistics.median(dx.values()):+.2f} mm, max {max(abs(v) for v in dx.values()):.2f} mm")
    for seuil in (0.3, 0.5, 1.0):
        sous = sum(abs(dy[k]) < seuil and abs(dx[k]) < seuil for k in communs)
        print(f"  sous {seuil:.1f} mm dans les deux sens : {sous} / {len(communs)}")
    ba, bn = bandeau(args.armony), bandeau(args.notre)
    if ba and bn:
        print(f"  bandeau : haut {bn[0] - ba[0]:+.2f} mm, bas {bn[1] - ba[1]:+.2f} mm")
    print(f"Plus grands écarts (négatif = plus haut / plus à gauche que chez Armony) :")
    for k in sorted(communs, key=lambda k: -max(abs(dy[k]), abs(dx[k])))[:args.detail]:
        print(f"  page {k[0] + 1}  dy {dy[k]:+.2f}  dx {dx[k]:+.2f}  {k[1][:60]}")
    print(f"Écart maximal : {pire:.2f} mm")


if __name__ == "__main__":
    main()
