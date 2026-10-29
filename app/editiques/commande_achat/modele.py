"""Ce que le bon de commande affiche, bloc par bloc, tel qu'Armony le met en page.

Les valeurs restent brutes (nombres décimaux, dates ISO) : le formatage à la
française appartient à la mise en page. Un champ que l'application n'a pas pu
lire vaut "" ou None, et la raison est dans `avertissements`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class BlocSociete:
    """Cadre en haut à gauche : la société qui passe commande (« client »)."""

    code: str = ""
    nom: str = ""
    siret: str = ""
    adresse_facturation: list[str] = field(default_factory=list)
    projet_ou_section: str = ""
    numero_projet: str = ""
    contact: str = ""
    mail: str = ""
    telephone: str = ""


@dataclass
class BlocFournisseur:
    code: str = ""
    nom: str = ""
    siret: str = ""
    adresse: list[str] = field(default_factory=list)
    contact: str = ""
    mail: str = ""
    conditions_paiement: str = ""
    mode_reglement: str = ""


@dataclass
class BlocLivraison:
    date: str = ""
    contact: str = ""
    adresse: list[str] = field(default_factory=list)
    horaires: str = ""
    commentaire: str = ""


@dataclass
class BlocFacturation:
    """« Modalités de facturation » : deux phrases IFS suivies d'une coordonnée."""

    sans_efacture: str = ""
    avec_efacture: str = ""


@dataclass
class Ligne:
    numero: str
    ref_client: str = ""
    ref_fournisseur: str = ""
    designation: str = ""
    unite: str = ""
    quantite: Decimal | None = None
    prix_unitaire: Decimal | None = None
    remise: Decimal | None = None
    montant_ht: Decimal | None = None
    taux_tva: Decimal | None = None
    # Ligne grisée sous l'article : « Contact, adresse et horaire de livraison : … »
    adresse_livraison: str = ""
    texte_document: str = ""


@dataclass
class Frais:
    designation: str = ""
    quantite: Decimal | None = None
    prix_unitaire: Decimal | None = None
    montant_ht: Decimal | None = None
    taux_tva: Decimal | None = None


@dataclass
class Annexe:
    """Un PDF joint après le bon de commande (les CGA)."""

    nom: str
    contenu: bytes = field(repr=False)


@dataclass
class CommandeAchat:
    numero: str
    etat: str = ""
    brouillon: bool = False
    date_commande: str = ""
    revision: str = ""
    societe: BlocSociete = field(default_factory=BlocSociete)
    fournisseur: BlocFournisseur = field(default_factory=BlocFournisseur)
    livraison: BlocLivraison = field(default_factory=BlocLivraison)
    facturation: BlocFacturation = field(default_factory=BlocFacturation)
    lignes: list[Ligne] = field(default_factory=list)
    frais: list[Frais] = field(default_factory=list)
    total_ht: Decimal | None = None
    phrases_document: list[str] = field(default_factory=list)
    pied_de_page: list[str] = field(default_factory=list)
    logo: bytes | None = field(default=None, repr=False)
    logo_type: str = "image/jpeg"
    annexes: list[Annexe] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)

    def en_dict(self) -> dict[str, Any]:
        """Vue JSON : les octets sont remplacés par leur taille, les décimaux par
        leur texte (un flottant ferait d'un 0,1 un 0,1000000000000000055)."""
        vue = asdict(self)
        vue["logo"] = f"{len(self.logo)} octets" if self.logo else None
        vue["annexes"] = [{"nom": a.nom, "taille": len(a.contenu)} for a in self.annexes]
        return _sans_decimaux(vue)


def _sans_decimaux(valeur: Any) -> Any:
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, dict):
        return {k: _sans_decimaux(v) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [_sans_decimaux(v) for v in valeur]
    return valeur
