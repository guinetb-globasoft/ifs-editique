"""Lire dans IFS tout ce que le bon de commande affiche.

Armony partait des données du rapport IFS `PURCHASE_ORDER_PRINT_REP` (PO_HEADERS,
PO_LINES… obtenues par l'impression) et les complétait par des requêtes. Ici,
**tout vient des projections OData, à partir du seul numéro de commande** : pas
d'impression IFS, donc pas d'effet de bord — « Imprimer commande » marque la
commande communiquée et ajoute une ligne d'historique (constaté par
tests-automatisés-IFS, 25/10/2026).

Deux lecteurs :

* **`utilisateur`** lit la commande elle-même (`PurchaseOrderHandling`, la
  projection de l'écran) : ce que l'utilisateur ne voit pas dans IFS, il ne
  l'imprime pas. Un échec ici arrête tout.
* **`reference`** lit le reste (société, coordinateur, phrases, logo, CGA) :
  c'est le compte technique s'il est configuré, sinon l'utilisateur. Un échec
  ici laisse le champ vide et ajoute un avertissement — le document part quand
  même, et `/donnees` dit ce qui manque.

Les noms IFS viennent du catalogue de métadonnées de CFG (mcp-ifs, moisson du
17/09/2026) ou des requêtes d'Armony en production : docs/specs/commande-achat.md,
colonne « Vérifié ».

**Les lectures partent en parallèle.** Une fois l'en-tête lu, tout ce qui n'en
dépend pas part en même temps ; seuls les adresses de projet et les textes
document attendent les lignes. Les textes document se lisent en une requête pour
toute la commande, pas une par ligne. En série, une vingtaine d'allers-retours
IFS s'additionnaient (constaté le 26/10/2026 : « beaucoup trop long »).

Quand Armony se comporte autrement que son script ne le laisse croire, c'est
**ce qu'Armony imprime** qui est reproduit, et l'écart est noté sur place.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, TypeVar

from ...config import DOSSIER_RESSOURCES
from ...ifs.lecture import ErreurIFS, Lecteur, litteral
from .modele import (
    Annexe,
    BlocFacturation,
    BlocFournisseur,
    BlocLivraison,
    BlocSociete,
    CommandeAchat,
    Frais,
    Ligne,
)

PO = "PurchaseOrderHandling.svc"
SELECT_LIGNE = ("LineNo,ReleaseNo,Objstate,VendorPartNo,Description,BuyUnitMeas,BuyQtyDue,"
                "FbuyUnitPrice,Discount,FeeCode,WantedDeliveryDate,NoteId,AddressId,ProjectId")
SELECT_FRAIS = "SequenceNo,Description,ChargedQty,ChargeAmount,TotalCurrency,FeeCode"

# Lectures IFS simultanées pour un document. Au-delà, on charge IFS sans gagner :
# la plus longue chaîne de lectures dépendantes en compte trois.
LECTURES_SIMULTANEES = 8
# NoteId par requête de textes document : un filtre « or » de 40 termes reste court.
NOTES_PAR_REQUETE = 40

# Phrases IFS du cadre « Modalités de facturation », comme dans Armony.
PHRASE_SANS_EFACTURE = "ACH05"
PHRASE_AVEC_EFACTURE = "ACH04"

# Les CGA jointes, repérées par leur nom de fichier dans les encarts PDF d'IFS.
CGA = {
    "achats": ("cga achat",),
    "location": ("cga location",),
    "prestation": ("cga prestation", "cga préstation"),
}

DOSSIER_TEXTES = DOSSIER_RESSOURCES / "textes"
DOSSIER_LOGOS = DOSSIER_RESSOURCES / "logos"

T = TypeVar("T")


class CommandeIntrouvable(LookupError):
    """IFS ne rend pas la commande : elle n'existe pas, ou l'utilisateur ne la voit pas."""


def lire_commande(utilisateur: Lecteur, reference: Lecteur, numero: str,
                  langue: str = "fr") -> CommandeAchat:
    numero = numero.strip().upper()
    lecture = _Lecture(reference)
    cle = f"{PO}/PurchaseOrderSet(OrderNo={litteral(numero)})"

    try:
        entete = utilisateur.lire_un(cle)
    except ErreurIFS as err:
        if err.statut in (403, 404):
            raise CommandeIntrouvable(
                f"La commande {numero} n'existe pas, ou vous n'y avez pas accès dans IFS."
            ) from err
        raise

    societe_code = _texte(entete, "Company")
    with ThreadPoolExecutor(max_workers=LECTURES_SIMULTANEES, thread_name_prefix="ifs") as fils:
        # Indispensables : leur échec remonte au .result().
        t_lignes = fils.submit(_lignes, utilisateur, cle)
        t_frais = fils.submit(utilisateur.lire, f"{cle}/PurchaseOrderChargeArray", {"$select": SELECT_FRAIS})
        # Le reste : un échec laisse un champ vide et un avertissement.
        t_taux = fils.submit(lecture.facultatif, "Taux de TVA",
                             lambda: _taux_tva(utilisateur, societe_code), {})
        t_montants = fils.submit(lecture.facultatif, "Montants de la commande",
                                 lambda: utilisateur.lire_un(f"{cle}/OrderAmountRef"), {})
        t_societe = fils.submit(_societe, entete, utilisateur, lecture, cle)
        t_fournisseur = fils.submit(_fournisseur, entete, utilisateur, lecture, cle)
        t_livraison = fils.submit(_livraison, entete, lecture)
        t_facturation = fils.submit(_facturation, entete, lecture, langue)
        t_logo = fils.submit(_logo, societe_code, lecture)
        t_cga = fils.submit(lecture.facultatif, "CGA", lambda: _cga(entete, reference), [])

        lignes_ifs = t_lignes.result()
        t_adresses = fils.submit(_adresses_de_projet, lignes_ifs, entete, utilisateur, lecture)
        notes = [n for n in (entete.get("NoteId"), *(l.get("NoteId") for l in lignes_ifs))
                 if n not in (None, "")]
        t_textes = fils.submit(lecture.facultatif, "Textes document",
                               lambda: _textes_document(lecture.reference, notes), {})
        frais_ifs = t_frais.result()

    taux = t_taux.result()
    commande = CommandeAchat(
        numero=numero,
        etat=_texte(entete, "Objstate"),
        # Armony titre « BROUILLON DE COMMANDE » une commande Planifiée.
        brouillon=_texte(entete, "Objstate") == "Planned",
        date_commande=_texte(entete, "OrderDate")[:10],
        revision=_entier(entete.get("Revision")),
        lignes=[_ligne(l, taux) for l in lignes_ifs],
        frais=[_frais(f, taux) for f in frais_ifs],
        societe=t_societe.result(),
        fournisseur=t_fournisseur.result(),
        livraison=t_livraison.result(),
        facturation=t_facturation.result(),
        annexes=t_cga.result(),
    )
    textes = t_textes.result()
    # Armony prend la date souhaitée de la première ligne.
    commande.livraison.date = _texte(lignes_ifs[0], "WantedDeliveryDate")[:10] if lignes_ifs else ""
    commande.livraison.horaires = ", ".join(textes.get(_note(entete.get("NoteId")), []))
    _details_des_lignes(commande.lignes, lignes_ifs, entete, t_adresses.result(), textes)
    commande.total_ht = _total(commande, t_montants.result(), lecture)

    textes_locaux = _textes_locaux(societe_code, lecture)
    commande.phrases_document = textes_locaux.get("phrases_document", [])
    commande.pied_de_page = textes_locaux.get("pied_de_page", [])
    commande.logo, commande.logo_type = t_logo.result()

    commande.avertissements = lecture.avertissements
    return commande


# ------------------------------------------------------------------ outillage
class _Lecture:
    """Le lecteur de référence, et les avertissements de ce qui n'a pu être lu."""

    def __init__(self, reference: Lecteur):
        self.reference = reference
        self.avertissements: list[str] = []

    def facultatif(self, quoi: str, fonction: Callable[[], T], defaut: T) -> T:
        try:
            return fonction()
        except ErreurIFS as err:
            self.avertissements.append(f"{quoi} non lu(e) : {err}")
            return defaut


def _texte(ligne: dict[str, Any] | None, champ: str) -> str:
    valeur = (ligne or {}).get(champ)
    return "" if valeur is None else str(valeur).strip()


def _decimal(valeur: Any) -> Decimal | None:
    return None if valeur in (None, "") else Decimal(str(valeur))


def _entier(valeur: Any) -> str:
    nombre = _decimal(valeur)
    return "" if nombre is None else str(int(nombre))


def _cle_tri(ligne: dict[str, Any]) -> tuple:
    def nombre(valeur: Any) -> tuple[int, str]:
        texte = str(valeur or "")
        return (int(texte), "") if texte.isdigit() else (0, texte)
    return nombre(ligne.get("LineNo")), nombre(ligne.get("ReleaseNo"))


def _non_vides(*valeurs: str) -> list[str]:
    return [v.strip() for v in valeurs if v and v.strip()]


# --------------------------------------------------------- lignes et frais
def _lignes(utilisateur: Lecteur, cle: str) -> list[dict[str, Any]]:
    """Lignes article puis sans article, réunies et triées comme le rapport IFS.

    Armony partait des lignes du rapport IFS (PO_LINES), qui ne reprend pas les
    lignes annulées : on les écarte aussi. ⚠️ À confirmer sur une commande réelle
    portant une ligne annulée (spec, question ouverte Q3).
    """
    articles = utilisateur.lire(f"{cle}/LinePartArray", {"$select": SELECT_LIGNE + ",PartNo,NetAmountBase"})
    # Les lignes sans article n'ont pas de PartNo, et nomment leur montant NetAmtBase.
    sans_article = utilisateur.lire(f"{cle}/LineNopartArray", {"$select": SELECT_LIGNE + ",NetAmtBase"})
    for ligne in sans_article:
        ligne["NetAmountBase"] = ligne.pop("NetAmtBase", None)
    lignes = [l for l in articles + sans_article if _texte(l, "Objstate") != "Cancelled"]
    return sorted(lignes, key=_cle_tri)


def _taux_tva(utilisateur: Lecteur, societe: str) -> dict[str, Decimal]:
    """Code taxe -> taux, pour la société de la commande (une lecture pour toutes les lignes)."""
    codes = utilisateur.lire(f"{PO}/Reference_TaxCodeCommon",
                             {"$filter": f"Company eq {litteral(societe)}",
                              "$select": "FeeCode,FeeRate"})
    return {c["FeeCode"]: _decimal(c.get("FeeRate")) for c in codes if c.get("FeeCode")}


def _ligne(ligne: dict[str, Any], taux: dict[str, Decimal]) -> Ligne:
    return Ligne(
        numero=f"{_texte(ligne, 'LineNo')}.{_texte(ligne, 'ReleaseNo')}",
        ref_client=_texte(ligne, "PartNo"),
        ref_fournisseur=_texte(ligne, "VendorPartNo"),
        designation=_texte(ligne, "Description"),
        unite=_texte(ligne, "BuyUnitMeas"),
        quantite=_decimal(ligne.get("BuyQtyDue")),
        prix_unitaire=_decimal(ligne.get("FbuyUnitPrice")),
        # Armony imprime « 0,00 » quand il n'y a pas de remise.
        remise=_decimal(ligne.get("Discount")) or Decimal(0),
        montant_ht=_decimal(ligne.get("NetAmountBase")),
        taux_tva=taux.get(_texte(ligne, "FeeCode")),
    )


def _frais(frais: dict[str, Any], taux: dict[str, Decimal]) -> Frais:
    return Frais(
        designation=_texte(frais, "Description"),
        quantite=_decimal(frais.get("ChargedQty")),
        prix_unitaire=_decimal(frais.get("ChargeAmount")),
        # Armony lisait NetAmountOrdCurr (projection d'entité) : montant net, devise de la commande.
        montant_ht=_decimal(frais.get("TotalCurrency")),
        taux_tva=taux.get(_texte(frais, "FeeCode")),
    )


AdressesDeProjet = tuple[dict[tuple[str, str], dict[str, Any]], dict[str, str]]


def _adresses_de_projet(lignes_ifs: list[dict[str, Any]], entete: dict[str, Any],
                        utilisateur: Lecteur, lecture: _Lecture) -> AdressesDeProjet:
    """Les adresses des projets de la commande, par (projet, adresse), et le nom des pays."""
    projets = {_texte(l, "ProjectId") for l in lignes_ifs} | {_texte(entete, "ProjectId")}
    adresses: dict[tuple[str, str], dict[str, Any]] = {}
    for projet in sorted(p for p in projets if p):
        for adresse in lecture.facultatif(
            f"Adresses du projet {projet}",
            lambda projet=projet: utilisateur.lire(f"{PO}/Reference_ProjectAddressLov",
                                                   {"$filter": f"ProjectId eq {litteral(projet)}"}),
            [],
        ):
            adresses[(projet, _texte(adresse, "AddressId"))] = adresse

    codes_pays = sorted({_texte(a, "Country") for a in adresses.values()} - {""})
    pays = lecture.facultatif("Noms de pays", lambda: _noms_de_pays(utilisateur, codes_pays), {})
    return adresses, pays


def _details_des_lignes(lignes: list[Ligne], lignes_ifs: list[dict[str, Any]],
                        entete: dict[str, Any], adresses_de_projet: AdressesDeProjet,
                        textes: dict[int, list[str]]) -> None:
    """Sous chaque ligne : l'adresse de livraison projet, puis ses textes document.

    Armony affiche « Contact, adresse et horaire de livraison : <nom>, <adresse>
    <contact> » quand la ligne est livrée à une adresse du projet. GA range
    l'horaire de livraison dans le champ Contact de l'adresse projet, d'où
    l'ordre du libellé.
    """
    adresses, pays = adresses_de_projet
    for ligne, source in zip(lignes, lignes_ifs):
        projet = _texte(source, "ProjectId") or _texte(entete, "ProjectId")
        adresse = adresses.get((projet, _texte(source, "AddressId")))
        if adresse:
            # « <nom>,  <adresse> <contact> » : Armony accole « <nom>, » et l'adresse
            # par une espace, d'où les deux espaces après la virgule.
            nom = _texte(adresse, "AddressName")
            reste = " ".join(_non_vides(_adresse_sur_une_ligne(adresse, pays),
                                        _texte(adresse, "Contact")))
            ligne.adresse_livraison = f"{nom},  {reste}" if nom else reste
        ligne.texte_document = ", ".join(textes.get(_note(source.get("NoteId")), []))


def _noms_de_pays(utilisateur: Lecteur, codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    filtre = " or ".join(f"CountryCode eq {litteral(c)}" for c in codes)
    return {_texte(p, "CountryCode"): _texte(p, "Description")
            for p in utilisateur.lire(f"{PO}/Reference_IsoCountry", {"$filter": filtre})}


def _adresse_sur_une_ligne(adresse: dict[str, Any], pays: dict[str, str]) -> str:
    """« ZA de la plaine, 68190 - ENSISHEIM, Haut-Rhin, FR - FRANCE », comme le rapport IFS."""
    rues = [_texte(adresse, f"Address{i}") for i in range(1, 7)]
    ville = " - ".join(_non_vides(_texte(adresse, "ZipCode"), _texte(adresse, "City")))
    code = _texte(adresse, "Country")
    return ", ".join(_non_vides(*rues, ville, _texte(adresse, "County"),
                                " - ".join(_non_vides(code, pays.get(code, "")))))


def _note(valeur: Any) -> int | None:
    """Un NoteId tel qu'IFS le rend (nombre ou texte) -> entier, ou None."""
    return None if valeur in (None, "") else int(Decimal(str(valeur)))


def _textes_document(reference: Lecteur, notes: list[Any]) -> dict[int, list[str]]:
    """Les textes document de tous les NoteId de la commande, par NoteId.

    Une requête pour toute la commande (par paquets de NOTES_PAR_REQUETE), et non
    une par ligne : sur une commande de 100 lignes, c'était 100 allers-retours.
    Le regroupement se fait sur la réponse, quel que soit le filtre appliqué.

    ⚠️ Tous types de sortie confondus : le rapport IFS ne retient que ceux
    rattachés au rapport, liste encore inconnue (spec, Q6).
    """
    uniques = sorted({n for n in map(_note, notes) if n is not None})
    par_note: dict[int, list[str]] = {}
    for debut in range(0, len(uniques), NOTES_PAR_REQUETE):
        paquet = uniques[debut:debut + NOTES_PAR_REQUETE]
        filtre = " or ".join(f"NoteId eq {n}" for n in paquet)
        for texte in reference.lire("DocumentTextHandling.svc/Reference_DocumentText", {"$filter": filtre}):
            note, contenu = _note(texte.get("NoteId")), _texte(texte, "NoteText")
            if note in paquet and contenu:
                par_note.setdefault(note, []).append(contenu)
    return par_note


def _total(commande: CommandeAchat, montants: dict[str, Any], lecture: _Lecture) -> Decimal | None:
    """Le total HT d'IFS, contrôlé contre la somme des lignes et frais imprimés."""
    somme = sum((x.montant_ht or Decimal(0) for x in [*commande.lignes, *commande.frais]),
                Decimal(0))
    total = _decimal(montants.get("OrderTotalCurr"))
    if total is None:
        return somme
    if abs(total - somme) > Decimal("0.01"):
        lecture.avertissements.append(
            f"Total HT d'IFS ({total}) différent de la somme des lignes et frais imprimés ({somme}).")
    return total


# ------------------------------------------------------------------ cadres
def _societe(entete: dict[str, Any], utilisateur: Lecteur, lecture: _Lecture, cle: str) -> BlocSociete:
    societe = _texte(entete, "Company")
    adresse_doc = _texte(entete, "DocumentAddressId")
    bloc = BlocSociete(
        code=societe,
        # Armony a deux branches (projet / section) mais sa condition rend « projet »
        # toujours vrai : il imprime le nom du projet, vide sans projet.
        projet_ou_section=_texte(entete, "ProjectName"),
        numero_projet=_texte(entete, "ProjectId"),
        contact=_texte(entete, "AuthorizerName"),
    )
    bloc.nom = _texte(lecture.facultatif(
        "Nom de la société", lambda: utilisateur.lire_un(f"{cle}/CompanyFinanceRef"), {}), "Description")

    adresse = lecture.facultatif("Adresse de facturation", lambda: utilisateur.lire(
        f"{PO}/Reference_CompanyAddress",
        {"$filter": f"Company eq {litteral(societe)} and AddressId eq {litteral(adresse_doc)}"}), [])
    if adresse:
        a = adresse[0]
        # Armony : adresse 1, adresse 2, puis « code postal ville ».
        bloc.adresse_facturation = _non_vides(
            _texte(a, "Address1"), _texte(a, "Address2"),
            " ".join(_non_vides(_texte(a, "ZipCode"), _texte(a, "City"))))

    numeros = lecture.facultatif("SIRET de la société", lambda: lecture.reference.lire(
        "CompanyHandling.svc/Reference_CompanyAddressTaxNumber",
        {"$filter": f"Company eq {litteral(societe)} and AddressId eq {litteral(adresse_doc)}"}), [])
    bloc.siret = next((_texte(n, "TaxIdNumber") for n in numeros if _texte(n, "TaxIdType") == "SIRET"), "")

    coordinateur = _texte(entete, "AuthorizeCode")
    if coordinateur:
        moyens = lecture.facultatif("Coordonnées du coordinateur", lambda: lecture.reference.lire(
            "PersonHandling.svc/Reference_CommMethod",
            {"$filter": f"Identity eq {litteral(coordinateur)}"}), [])
        bloc.mail = _moyen(moyens, "EMail")
        bloc.telephone = _moyen(moyens, "Phone") or _moyen(moyens, "Mobile")
    return bloc


def _moyen(moyens: list[dict[str, Any]], methode: str, adresse: str | None = None) -> str:
    """La valeur d'un moyen de communication, le moyen par défaut d'abord."""
    candidats = [m for m in moyens if _texte(m, "MethodId") == methode
                 and (adresse is None or _texte(m, "AddressId") == adresse)]
    candidats.sort(key=lambda m: not m.get("MethodDefault"))
    return _texte(candidats[0], "Value") if candidats else ""


def _fournisseur(entete: dict[str, Any], utilisateur: Lecteur, lecture: _Lecture, cle: str) -> BlocFournisseur:
    fournisseur = _texte(entete, "VendorNo")
    societe = _texte(entete, "Company")
    # Chez GA, l'identifiant de l'adresse document du fournisseur est son SIRET :
    # c'est lui qu'Armony imprime derrière « SIRET : ».
    adresse_doc = _texte(entete, "DocAddrNo") or _texte(entete, "AddrNo")
    bloc = BlocFournisseur(code=fournisseur, nom=_texte(entete, "VendorName"), siret=adresse_doc,
                           contact=_texte(entete, "ContactName"))

    adresses = lecture.facultatif("Adresse du fournisseur", lambda: utilisateur.lire(
        f"{PO}/Reference_SupplierInfoAddress",
        {"$filter": f"SupplierId eq {litteral(fournisseur)} and AddressId eq {litteral(adresse_doc)}"}), [])
    if adresses:
        a = adresses[0]
        lignes = _non_vides(*(_texte(a, f"Address{i}") for i in range(1, 7)),
                            " ".join(_non_vides(_texte(a, "ZipCode"), _texte(a, "City"))))
        # Armony n'imprime que les deux premières lignes de l'adresse.
        bloc.adresse = lignes[:2]

    bloc.conditions_paiement = _texte(lecture.facultatif(
        "Conditions de paiement", lambda: utilisateur.lire_un(f"{cle}/PayTermIdRef"), {}), "Description")

    moyens = lecture.facultatif("E-mail du fournisseur", lambda: lecture.reference.lire(
        "SupplierHandling.svc/Reference_CommMethod",
        {"$filter": f"Identity eq {litteral(fournisseur)} and AddressId eq {litteral(adresse_doc)}"}), [])
    bloc.mail = _moyen([m for m in moyens if _texte(m, "PartyType") in ("", "Supplier")], "EMail")

    bloc.mode_reglement = lecture.facultatif(
        "Mode de règlement", lambda: _mode_reglement(lecture.reference, fournisseur, societe), "")
    return bloc


def _mode_reglement(reference: Lecteur, fournisseur: str, societe: str) -> str:
    """Le mode de paiement par défaut du fournisseur pour la société de la commande."""
    modes = reference.lire("SupplierHandling.svc/Reference_PaymentWayPerIdentity",
                           {"$filter": f"Identity eq {litteral(fournisseur)} and Company eq {litteral(societe)}"})
    defaut = next((m for m in modes if m.get("DefaultPaymentWay")
                   and _texte(m, "PartyType") in ("", "Supplier")), None)
    if not defaut:
        return ""
    libelles = reference.lire("SupplierHandling.svc/Reference_PaymentWay",
                              {"$filter": f"Company eq {litteral(societe)} and WayId eq {litteral(_texte(defaut, 'WayId'))}"})
    return _texte(libelles[0], "Description") if libelles else ""


def _livraison(entete: dict[str, Any], lecture: _Lecture) -> BlocLivraison:
    """Le cadre livraison, sauf la date et les textes document, qui attendent les lignes."""
    bloc = BlocLivraison(
        adresse=_non_vides(*(_texte(entete, f"Address{i}") for i in range(1, 7))),
        commentaire=_texte(entete, "LabelNote"),
    )
    projet, adresse_projet = _texte(entete, "ProjectId"), _texte(entete, "ProjectAddressId")
    contact = ""
    if projet and adresse_projet:
        moyens = lecture.facultatif("Contact de livraison du projet", lambda: lecture.reference.lire(
            "ProjectDefinitionHandling.svc/Reference_ProjectCommMethod",
            {"$filter": f"ProjectId eq {litteral(projet)} and AddressId eq {litteral(adresse_projet)}"}), [])
        courriel = next((m for m in moyens if _texte(m, "MethodId") == "EMail"), None)
        if courriel:
            contact = ", ".join(_non_vides(_texte(courriel, "Name"), _texte(courriel, "Value")))
    bloc.contact = ", ".join(_non_vides(contact, _texte(entete, "Reference")))
    return bloc


def _facturation(entete: dict[str, Any], lecture: _Lecture, langue: str) -> BlocFacturation:
    societe, adresse_doc = _texte(entete, "Company"), _texte(entete, "DocumentAddressId")
    phrases = lecture.facultatif("Phrases ACH04 / ACH05", lambda: lecture.reference.lire(
        "PhrasesHandling.svc/Reference_MpccomPhraseText",
        {"$filter": f"PhraseId eq {litteral(PHRASE_AVEC_EFACTURE)} or PhraseId eq {litteral(PHRASE_SANS_EFACTURE)}"}), [])
    moyens = lecture.facultatif("E-mails de facturation de la société", lambda: lecture.reference.lire(
        "CompanyHandling.svc/Reference_CommMethod",
        {"$filter": f"Identity eq {litteral(societe)} and AddressId eq {litteral(adresse_doc)}"}), [])
    moyens = [m for m in moyens if _texte(m, "PartyType") in ("", "Company")]
    return BlocFacturation(
        sans_efacture=" ".join(_non_vides(_phrase(phrases, PHRASE_SANS_EFACTURE, langue),
                                          _moyen(moyens, "EMail"))),
        # « Messenger » porte, chez GA, l'identifiant de routage de la plateforme agréée.
        avec_efacture=" ".join(_non_vides(_phrase(phrases, PHRASE_AVEC_EFACTURE, langue),
                                          _moyen(moyens, "Messenger"))),
    )


def _phrase(phrases: list[dict[str, Any]], identifiant: str, langue: str) -> str:
    candidates = [p for p in phrases if _texte(p, "PhraseId") == identifiant]
    candidates.sort(key=lambda p: _texte(p, "LanguageCode").lower() != langue.lower())
    return _texte(candidates[0], "PhraseText") if candidates else ""


# ----------------------------------------------------- logo, CGA, textes fixes
def _logo(societe: str, lecture: _Lecture) -> tuple[bytes | None, str]:
    """Le logo de la société dans IFS.

    Une société sans logo dans IFS n'en a pas sur le document, comme dans Armony.
    Le logo des ressources ne sert que si IFS n'a pas pu être lu (droits) : un
    bon de commande sans logo pour une raison technique se remarquerait trop tard.
    """
    def depuis_ifs() -> tuple[bytes | None, str]:
        nom = _texte(lecture.reference.lire_un(f"CompanyHandling.svc/CompanySet(Company={litteral(societe)})",
                                               {"$select": "Company,Logotype"}), "Logotype")
        if not nom:
            return None, ""
        octets = lecture.reference.lire_binaire(
            f"ReportImagesHandling.svc/ReportLogoSet(ImageName={litteral(nom)})/FileData")
        return octets, _type_image(nom)

    # Pas de lecture.facultatif ici : il faut savoir si C'EST le logo qui a échoué,
    # et compter les avertissements ne le dit plus quand les lectures sont parallèles.
    try:
        return depuis_ifs()
    except ErreurIFS as err:
        lecture.avertissements.append(f"Logo de la société non lu : {err}")
    for nom in (f"{societe}.png", f"{societe}.jpg", "defaut.png"):
        chemin = DOSSIER_LOGOS / nom
        if chemin.exists():
            return chemin.read_bytes(), _type_image(nom)
    return None, ""


def _type_image(nom: str) -> str:
    extension = Path(nom).suffix.lower()
    return {".png": "image/png", ".gif": "image/gif", ".svg": "image/svg+xml"}.get(extension, "image/jpeg")


def _cga(entete: dict[str, Any], reference: Lecteur) -> list[Annexe]:
    """Les CGA à joindre, choisies par les cases CUSTOM de la commande.

    Règle d'Armony : CGA achat si la case Achats est cochée **ou si aucune ne
    l'est** ; CGA location et prestation si leur case est cochée.
    """
    achats, location, prestation = (bool(entete.get(f"Cf_Ga_Cdeha_{c}"))
                                    for c in ("Achats", "Location", "Prestation"))
    voulues = [c for c, oui in (("achats", achats or not (location or prestation)),
                                ("location", location), ("prestation", prestation)) if oui]
    encarts = reference.lire("PdfInsertsHandling.svc/ReportPdfInserts", {"$select": "Id,FileName,FileDate"})
    annexes = []
    for categorie in voulues:
        candidats = [e for e in encarts
                     if any(m in _texte(e, "FileName").lower() for m in CGA[categorie])]
        if not candidats:
            raise ErreurIFS(f"aucun encart PDF « {CGA[categorie][0]} » dans IFS")
        # Plusieurs versions d'une même CGA : la plus récente.
        encart = max(candidats, key=lambda e: _texte(e, "FileDate"))
        annexes.append(Annexe(_texte(encart, "FileName"), reference.lire_binaire(
            f"PdfInsertsHandling.svc/ReportPdfInserts(Id={litteral(_texte(encart, 'Id'))})/FileData")))
    return annexes


def _textes_locaux(societe: str, lecture: _Lecture) -> dict[str, list[str]]:
    """Mentions sous le tableau et pied de page, par société, lus dans `ressources/textes`.

    ⚠️ Provisoire. Armony les reçoit calculés par le rapport IFS (DOC_PHRASES,
    DOCUMENT_FOOTERS) ; leur source OData n'est pas encore identifiée — aucun rôle
    de CFG, même GAIFS_RF_ARMONY, n'ouvre DocumentFooterHandling.
    """
    chemin = DOSSIER_TEXTES / f"{societe}.json"
    if not chemin.exists():
        lecture.avertissements.append(
            f"Mentions et pied de page absents : pas de fichier ressources/textes/{societe}.json.")
        return {}
    return json.loads(chemin.read_text(encoding="utf-8"))
