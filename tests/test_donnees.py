"""Les règles du bon de commande, reprises d'Armony (docs/specs/commande-achat.md)."""

from decimal import Decimal

import pytest

from app.editiques.commande_achat.donnees import CommandeIntrouvable, lire_commande
from app.ifs.lecture import ErreurIFS
from tests.conftest import CLE

LIGNES_SA = f"{CLE}/LineNopartArray"
LIGNES_A = f"{CLE}/LinePartArray"


def lire(lecteur, reference=None):
    return lire_commande(lecteur, reference or lecteur, "C106553")


# ------------------------------------------------------------------ en-tête
def test_entete_comme_sur_le_pdf_armony(lecteur):
    c = lire(lecteur)
    assert (c.numero, c.date_commande, c.revision, c.brouillon) == ("C106553", "2026-10-14", "0", False)
    assert c.societe.nom == "GA ENTREPRISE SAS"
    assert c.societe.siret == "42826603500123"
    assert c.societe.adresse_facturation == ["33 Piste des Géants", "CS 27751", "31077 TOULOUSE CEDEX 4"]
    assert (c.societe.projet_ou_section, c.societe.numero_projet) == ("Ensisheim LCP EUROVIA 16", "CHQ008")
    assert (c.societe.contact, c.societe.mail, c.societe.telephone) == (
        "Camille MARTIN", "camille.martin@exemple.fr", "+33 6 00 00 00 00")
    assert c.avertissements == []


def test_numero_saisi_en_minuscules(lecteur):
    assert lire_commande(lecteur, lecteur, " c106553 ").numero == "C106553"


def test_commande_planifiee_titree_brouillon(lecteur):
    lecteur.reponses[CLE]["Objstate"] = "Planned"
    assert lire(lecteur).brouillon is True


def test_commande_invisible_pour_l_utilisateur(lecteur):
    del lecteur.reponses[CLE]
    with pytest.raises(CommandeIntrouvable):
        lire(lecteur)


def test_fournisseur(lecteur):
    f = lire(lecteur).fournisseur
    assert (f.nom, f.siret) == ("ALGECO", "68555065900534")
    assert f.mail == "service.commercial@algeco.com"
    assert f.conditions_paiement == "Paiement à 30 jours fin de mois le 15"
    assert f.mode_reglement == "VIREMENT SEPA"


def test_adresse_fournisseur_limitee_a_deux_lignes(lecteur):
    # Armony : SplitLines puis DataRowNumber < 3.
    assert lire(lecteur).fournisseur.adresse == ["ESPACE DES BERTHILLIERS", "164 CHEMIN DE BALME"]


def test_livraison(lecteur):
    l = lire(lecteur).livraison
    assert l.date == "2026-10-14"
    assert l.adresse == ["33 Piste des Géants", "CS 27751"]
    assert (l.contact, l.horaires, l.commentaire) == ("", "", "")


def test_contact_de_livraison_du_projet_et_reference(lecteur):
    lecteur.reponses[CLE].update(ProjectAddressId="LCP", Reference="REF-42")
    lecteur.reponses["ProjectDefinitionHandling.svc/Reference_ProjectCommMethod"] = [
        {"ProjectId": "CHQ008", "AddressId": "LCP", "MethodId": "EMail",
         "Name": "Accueil chantier", "Value": "chantier@exemple.fr"}]
    assert lire(lecteur).livraison.contact == "Accueil chantier, chantier@exemple.fr, REF-42"


TEXTES = "DocumentTextHandling.svc/Reference_DocumentText"


def test_textes_document_de_l_entete_dans_le_cadre_livraison(lecteur):
    lecteur.reponses[TEXTES] = [
        {"NoteId": 1001, "OutputType": "PO", "NoteText": "Livraison de 7h à 12h"},
        {"NoteId": 1001, "OutputType": "PO", "NoteText": "Appeler la veille"}]
    assert lire(lecteur).livraison.horaires == "Livraison de 7h à 12h, Appeler la veille"


def test_textes_document_lus_en_une_requete_pour_toute_la_commande(lecteur):
    lecteur.reponses[TEXTES] = [{"NoteId": 1002, "NoteText": "Couleur RAL 9010"}]
    for numero in range(2, 6):
        lecteur.reponses[LIGNES_SA].append(dict(lecteur.reponses[LIGNES_SA][0], LineNo=str(numero),
                                                NoteId=2000 + numero))
    c = lire(lecteur)
    assert [l.texte_document for l in c.lignes] == ["Couleur RAL 9010", "", "", "", ""]
    lectures = [a for a in lecteur.journal if a.chemin.startswith(TEXTES)]
    assert len(lectures) == 1


def test_modalites_de_facturation(lecteur):
    f = lire(lecteur).facturation
    assert f.sans_efacture.endswith("mail à utiliser : facturegae@ga.fr")
    assert f.avec_efacture.endswith("notre plateforme agréée : 428266035")


# ------------------------------------------------------------------- lignes
def test_ligne_sans_article(lecteur):
    [l] = lire(lecteur).lignes
    assert (l.ref_client, l.designation, l.unite) == ("", "marteau", "PCS")
    assert (l.quantite, l.prix_unitaire, l.remise, l.montant_ht, l.taux_tva) == (
        Decimal(1), Decimal(2000), Decimal(0), Decimal(2000), Decimal(20))


def test_ligne_livree_a_une_adresse_du_projet(lecteur):
    [l] = lire(lecteur).lignes
    # Deux espaces après la virgule : ceux d'Armony, qui décident de la coupure de ligne.
    assert l.adresse_livraison == ("LCP EUROVIA,  ZA de la plaine d'Alsace, 68190 - ENSISHEIM, "
                                   "Haut-Rhin, FR - FRANCE de 7h30 à 17h30")


def test_ligne_hors_adresse_projet_sans_detail(lecteur):
    lecteur.reponses[LIGNES_SA][0]["AddressId"] = "SIEGE"
    assert lire(lecteur).lignes[0].adresse_livraison == ""


def test_remise_absente_imprimee_zero(lecteur):
    lecteur.reponses[LIGNES_SA][0]["Discount"] = None
    assert lire(lecteur).lignes[0].remise == Decimal(0)


def test_lignes_article_et_sans_article_triees_par_numero(lecteur):
    article = dict(lecteur.reponses[LIGNES_SA][0], LineNo="2", PartNo="ART-1",
                   NetAmountBase=50, Description="vis")
    article.pop("NetAmtBase")
    lecteur.reponses[LIGNES_A] = [dict(article, LineNo="10"), article]
    lignes = lire(lecteur).lignes
    assert [l.numero for l in lignes] == ["1.1", "2.1", "10.1"]
    assert lignes[1].ref_client == "ART-1" and lignes[1].montant_ht == Decimal(50)


def test_ligne_annulee_non_imprimee(lecteur):
    annulee = dict(lecteur.reponses[LIGNES_SA][0], LineNo="2", Objstate="Cancelled")
    lecteur.reponses[LIGNES_SA].append(annulee)
    assert [l.numero for l in lire(lecteur).lignes] == ["1.1"]


def test_texte_document_de_ligne(lecteur):
    lecteur.reponses[TEXTES] = [{"NoteId": 1002, "OutputType": "PO", "NoteText": "Couleur RAL 9010"}]
    assert lire(lecteur).lignes[0].texte_document == "Couleur RAL 9010"


def test_frais(lecteur):
    lecteur.reponses[f"{CLE}/PurchaseOrderChargeArray"] = [
        {"SequenceNo": 1, "Description": "Transport", "ChargedQty": 1, "ChargeAmount": 80,
         "TotalCurrency": 80, "FeeCode": "20"}]
    lecteur.reponses[f"{CLE}/OrderAmountRef"]["OrderTotalCurr"] = 2080
    c = lire(lecteur)
    [f] = c.frais
    assert (f.designation, f.montant_ht, f.taux_tva) == ("Transport", Decimal(80), Decimal(20))
    assert c.total_ht == Decimal(2080) and c.avertissements == []


def test_total_ifs_ecart_signale(lecteur):
    lecteur.reponses[f"{CLE}/OrderAmountRef"]["OrderTotalCurr"] = 1999
    c = lire(lecteur)
    assert c.total_ht == Decimal(1999)
    assert any("Total HT d'IFS" in a for a in c.avertissements)


# --------------------------------------------------------------------- CGA
@pytest.mark.parametrize("cases, attendues", [
    ({}, ["CGA ACHAT"]),                                    # aucune case : CGA achat
    ({"Cf_Ga_Cdeha_Location": True}, ["CGA LOCATION"]),
    ({"Cf_Ga_Cdeha_Achats": True, "Cf_Ga_Cdeha_Prestation": True}, ["CGA ACHAT", "CGA PRESTATION"]),
    ({"Cf_Ga_Cdeha_Location": True, "Cf_Ga_Cdeha_Prestation": True}, ["CGA LOCATION", "CGA PRESTATION"]),
])
def test_choix_des_cga(lecteur, cases, attendues):
    lecteur.reponses[CLE].update(cases)
    noms = [a.nom.upper() for a in lire(lecteur).annexes]
    assert [next(m for m in attendues if n.startswith(m)) for n in noms] == attendues


def test_cga_la_plus_recente(lecteur):
    lecteur.reponses["PdfInsertsHandling.svc/ReportPdfInserts"].append(
        {"Id": "CGA9", "FileName": "CGA achat 2026.pdf", "FileDate": "2026-09-01"})
    lecteur.binaires["PdfInsertsHandling.svc/ReportPdfInserts(Id='CGA9')/FileData"] = b"%PDF-1.4"
    assert [a.nom for a in lire(lecteur).annexes] == ["CGA achat 2026.pdf"]


def test_cga_introuvable_signalee(lecteur):
    lecteur.reponses["PdfInsertsHandling.svc/ReportPdfInserts"] = []
    c = lire(lecteur)
    assert c.annexes == [] and any("CGA" in a for a in c.avertissements)


# ------------------------------------------- ce qui manque ne bloque pas
class SansDroits:
    """Le lecteur de référence d'un acheteur : rien hors PurchaseOrderHandling."""

    def __init__(self, lecteur):
        self.l, self.journal = lecteur, []

    def _verifier(self, chemin):
        if not chemin.startswith("PurchaseOrderHandling.svc"):
            raise ErreurIFS(f"{chemin} : 403 Forbidden", 403)

    def lire(self, chemin, params=None):
        self._verifier(chemin)
        return self.l.lire(chemin, params)

    def lire_un(self, chemin, params=None):
        self._verifier(chemin)
        return self.l.lire_un(chemin, params)

    def lire_binaire(self, chemin):
        self._verifier(chemin)
        return self.l.lire_binaire(chemin)


def test_acheteur_sans_compte_technique_document_produit_avec_avertissements(lecteur):
    c = lire(lecteur, SansDroits(lecteur))
    assert c.lignes and c.societe.nom == "GA ENTREPRISE SAS"        # PurchaseOrderHandling : lu
    assert c.societe.siret == "" and c.facturation.sans_efacture == ""  # CompanyHandling : refusé
    assert c.annexes == []
    assert c.logo is not None                                       # repli sur le logo des ressources
    manques = " ".join(c.avertissements)
    for quoi in ("SIRET", "coordinateur", "ACH04", "CGA", "Logo"):
        assert quoi in manques


def test_societe_sans_logo_dans_ifs_pas_de_logo(lecteur):
    lecteur.reponses["CompanyHandling.svc/CompanySet(Company='GAE')"]["Logotype"] = None
    c = lire(lecteur)
    assert c.logo is None and c.avertissements == []


def test_societe_sans_textes_locaux_signalee(lecteur):
    lecteur.reponses[CLE]["Company"] = "ZZZ"
    c = lire(lecteur)
    assert c.phrases_document == [] and c.pied_de_page == []
    assert any("ressources/textes/ZZZ.json" in a for a in c.avertissements)
