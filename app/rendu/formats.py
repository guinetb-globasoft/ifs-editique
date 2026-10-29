"""Nombres et dates à la française, comme Armony les imprime.

Armony formate avec `### #### ### ##0.00` en culture `fr` : « 2 000,00 ». Le
séparateur de milliers est ici une espace insécable, pour qu'un montant ne se
coupe jamais en fin de ligne d'une colonne étroite.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

INSECABLE = " "


def nombre(valeur: Decimal | float | int | None, decimales: int = 2) -> str:
    """2000 -> « 2 000,00 » ; None -> « »."""
    if valeur is None or valeur == "":
        return ""
    arrondi = Decimal(str(valeur)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    signe = "-" if arrondi < 0 else ""
    entier, _, fraction = f"{abs(arrondi):f}".partition(".")
    groupes = []
    while len(entier) > 3:
        entier, groupes = entier[:-3], [entier[-3:], *groupes]
    texte = INSECABLE.join([entier, *groupes])
    return f"{signe}{texte},{fraction}" if decimales else f"{signe}{texte}"


def montant_euros(valeur: Decimal | float | int | None) -> str:
    """2000 -> « 2 000,00 € » (format `### #### ### ##0.00 €` d'Armony)."""
    texte = nombre(valeur)
    return f"{texte}{INSECABLE}€" if texte else ""


def date_fr(valeur: str | None) -> str:
    """« 2026-10-14 » ou « 2026-10-14T00:00:00Z » -> « 14/10/2026 ».

    On ne prend que la partie date, sans conversion de fuseau : sans l'en-tête
    `x-ifs-time-zone-aware-request`, IFS rend la valeur telle qu'elle est
    enregistrée.
    """
    if not valeur or len(valeur) < 10:
        return ""
    annee, mois, jour = valeur[:10].split("-")
    return f"{jour}/{mois}/{annee}"
