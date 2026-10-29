"""HTML -> PDF par Chromium (Playwright), puis concaténation des annexes.

Pourquoi Chromium : le gabarit est du HTML/CSS qu'on lit et modifie sans outil
dédié, l'en-tête de tableau se répète seul d'une page à l'autre, et l'en-tête et
le pied de page de Chromium savent numéroter « 1/2 ». Playwright 1.58.0 est déjà
la version de tests-automatisés-IFS : les navigateurs installés servent aux deux.

**Un seul Chromium, lancé une fois, dans un fil qui lui est réservé.** Le lancer
coûte 3,7 s, rendre une page 0,7 s (mesuré le 26/10/2026) : le relancer à chaque
document faisait l'essentiel de l'attente. Les objets Playwright « sync » ne
passent pas d'un fil à l'autre ; les requêtes, servies par plusieurs fils, confient
donc leur rendu à ce fil unique, l'un après l'autre.
"""

from __future__ import annotations

import io
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from playwright.sync_api import Browser, sync_playwright
from pypdf import PdfReader, PdfWriter

_fil = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chromium")
_local = threading.local()


def _navigateur() -> Browser:
    """Le Chromium du fil de rendu, relancé s'il est tombé."""
    navigateur = getattr(_local, "navigateur", None)
    if navigateur is None or not navigateur.is_connected():
        if getattr(_local, "playwright", None) is None:
            _local.playwright = sync_playwright().start()
        _local.navigateur = _local.playwright.chromium.launch()
    return _local.navigateur


def _rendre(corps: str, entete: str, pied: str, marges: dict[str, str]) -> bytes:
    page = _navigateur().new_page()
    try:
        page.set_content(corps, wait_until="load")
        return page.pdf(
            # 210 x 297 mm exactement : `format="A4"` donne 8,27 x 11,7 pouces,
            # soit une feuille un rien plus grande que celle d'Armony.
            width="210mm",
            height="297mm",
            print_background=True,
            display_header_footer=True,
            header_template=entete,
            footer_template=pied,
            margin=marges,
        )
    finally:
        page.close()


def _arreter() -> None:
    navigateur = getattr(_local, "navigateur", None)
    if navigateur is not None and navigateur.is_connected():
        navigateur.close()
    if getattr(_local, "playwright", None) is not None:
        _local.playwright.stop()
        _local.playwright = None


def demarrer() -> Future:
    """Lance Chromium sans attendre : le premier clic n'en paiera pas le coût."""
    return _fil.submit(_navigateur)


def arreter() -> None:
    _fil.submit(_arreter).result()


def html_vers_pdf(corps: str, entete: str, pied: str, marges: dict[str, str]) -> bytes:
    return _fil.submit(_rendre, corps, entete, pied, marges).result()


def concatener(principal: bytes, annexes: list[bytes]) -> bytes:
    """Le document, puis chaque annexe dans l'ordre. La numérotation « n/N » du
    document ne compte pas les annexes, comme dans Armony."""
    if not annexes:
        return principal
    sortie = PdfWriter()
    for contenu in (principal, *annexes):
        sortie.append(PdfReader(io.BytesIO(contenu)))
    tampon = io.BytesIO()
    sortie.write(tampon)
    return tampon.getvalue()


def signer(contenu: bytes, titre: str, application: str) -> bytes:
    """Titre et application dans les propriétés du PDF : ce qui dit, depuis IFS ou un lecteur PDF, qui a produit
    le document et en quelle version (Armony signe « DynamicPDF »)."""
    sortie = PdfWriter(clone_from=PdfReader(io.BytesIO(contenu)))
    sortie.add_metadata({"/Title": titre, "/Creator": application, "/Producer": application})
    tampon = io.BytesIO()
    sortie.write(tampon)
    return tampon.getvalue()


def nombre_de_pages(contenu: bytes) -> int:
    return len(PdfReader(io.BytesIO(contenu)).pages)
