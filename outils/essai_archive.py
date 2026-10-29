"""Essai sur CFG : mettre notre PDF à la place de celui d'Armony dans l'archive IFS, puis remettre l'original.

C'est l'écriture que fera l'application branchée sur l'impression (D-008, spec § 5.3, étape 4), jouée sur des
impressions que l'on fait soi-même. Rien d'autre n'est écrit : ni configuration IFS, ni e-mail, ni état « imprimé ».

    .venv\\Scripts\\python.exe outils\\essai_archive.py dernieres              # mes dernières impressions de BDC
    .venv\\Scripts\\python.exe outils\\essai_archive.py voir <clé>              # lecture seule
    .venv\\Scripts\\python.exe outils\\essai_archive.py remplacer <clé> [<n°>]  # sauvegarde, puis notre PDF
    .venv\\Scripts\\python.exe outils\\essai_archive.py ecouter [--a-blanc]     # en direct : chaque nouvelle impression
    .venv\\Scripts\\python.exe outils\\essai_archive.py restaurer [<clé>]       # remet l'original (toutes sans clé)

`<clé>` est la clé d'archive (ResultKey) de l'impression. Les sauvegardes vont dans `sorties/essai_archive/` (hors
dépôt). Rien n'est écrit sans sauvegarde préalable, et une seconde exécution garde la première sauvegarde, celle
d'avant tout essai. `restaurer` relit l'archive et vérifie qu'elle rend le PDF sauvegardé, octet pour octet.

`ecouter` interroge l'archive toutes les quelques secondes et remplace le PDF « Armony layout » de chaque nouvelle
impression de bon de commande de l'utilisateur, jusqu'à Ctrl+C. Ce n'est pas IFS qui appelle (il ne joint pas un
poste) : l'aperçu peut s'afficher avant le remplacement, il faut alors le recharger.

⚠️ Outil d'essai, pas l'application. Le jeton est celui de l'utilisateur, obtenu par le client MCP_IFS du dépôt
voisin mcp-ifs (`outils/jeton.py`), qui ouvre le navigateur si la session a expiré.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app.config import config  # noqa: E402
from app.editiques.commande_achat import generer  # noqa: E402
from app.ifs import compte_technique  # noqa: E402
from app.ifs.lecture import ErreurIFS, LecteurIFS, litteral  # noqa: E402
from app.impression import numero_de_commande  # noqa: E402
from app.rendu import pdf  # noqa: E402

RAPPORT = "PURCHASE_ORDER_PRINT_REP"
DISPOSITION = "PurchaseOrderPrintRepArmony.rdl"
SAUVEGARDES = RACINE / "sorties" / "essai_archive"
MCP_IFS = RACINE.parent / "mcp-ifs"


class EssaiImpossible(RuntimeError):
    """L'essai s'arrête sans rien écrire (ou après une écriture vérifiée qui ne correspond pas)."""


def _module(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.cache
def _jeton_mcp_ifs():
    reglages = _module("mcp_ifs_reglages", MCP_IFS / "outils" / "reglages.py")
    reglages.charger_env(str(MCP_IFS / ".env"))
    return _module("mcp_ifs_jeton", MCP_IFS / "outils" / "jeton.py")


def jeton_utilisateur() -> str:
    """Le jeton IFS de l'utilisateur, frais (rafraîchi au besoin), par l'outil de développement de mcp-ifs."""
    return _jeton_mcp_ifs().jeton_valide()


def empreinte(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


class Archive:
    """Une impression archivée : ses lignes PdfArchive (lecture) et le remplacement de son PDF (écriture)."""

    def __init__(self, jeton: str, cle: int):
        self.jeton, self.cle = jeton, cle
        self.lecteur = LecteurIFS(jeton=jeton, base=config.url_projection, langue="fr-FR")

    def chemin_pdf(self, id_pdf: str) -> str:
        return f"PrintDialog.svc/PdfArchiveSet(ResultKey={self.cle},Id={litteral(id_pdf)})"

    def pdfs(self) -> list[dict]:
        return self.lecteur.lire("PrintDialog.svc/PdfArchiveSet", {"$filter": f"ResultKey eq {self.cle}"})

    def rapport(self) -> dict | None:
        lignes = self.lecteur.lire("ReportArchive.svc/ArchiveSet", {"$filter": f"ResultKey eq {self.cle}"})
        return lignes[0] if lignes else None

    def le_pdf(self) -> dict:
        """Le PDF « Armony layout » de la clé. Une clé peut en porter d'autres (même boîte, autre disposition) :
        ils ne sont pas touchés."""
        lignes = [l for l in self.pdfs() if l.get("LayoutName") == DISPOSITION]
        if len(lignes) != 1:
            raise EssaiImpossible(
                f"{len(lignes)} PDF {DISPOSITION} sous la clé {self.cle} : l'essai en attend exactement un "
                "(une impression que vous avez faite vous-même ; l'archive est cloisonnée par utilisateur).")
        return lignes[0]

    def telecharger(self, id_pdf: str) -> bytes:
        return self.lecteur.lire_binaire(self.chemin_pdf(id_pdf) + "/Pdf")

    def ecrire(self, id_pdf: str, etag: str, contenu: bytes) -> None:
        """La seule écriture de l'essai : PATCH du flux Pdf, comme le connecteur Armony (If-Match)."""
        reponse = requests.patch(
            f"{config.url_projection}/{self.chemin_pdf(id_pdf)}/Pdf",
            data=contenu,
            headers={"Authorization": f"Bearer {self.jeton}", "If-Match": etag,
                     "Content-Type": "application/octet-stream", "Accept-Language": "fr-FR"},
            timeout=120,
        )
        if not reponse.ok:
            raise EssaiImpossible(f"IFS a refusé l'écriture : {reponse.status_code} {reponse.text[:400]}")


def fichiers(cle: int) -> tuple[Path, Path]:
    return SAUVEGARDES / f"{cle}.json", SAUVEGARDES / f"{cle}_avant.pdf"


def derniers_pdfs(jeton: str, combien: int = 8) -> list[dict]:
    """Les derniers PDF « Armony layout » de l'archive. `ArchiveSet` ne les montre pas tous (constaté sur CFG le
    29/10/2026) ; `$select` sur `ArchiveSet` y rend 400."""
    lecteur = LecteurIFS(jeton=jeton, base=config.url_projection, langue="fr-FR")
    return lecteur.lire_un("PrintDialog.svc/PdfArchiveSet", {
        "$filter": f"LayoutName eq '{DISPOSITION}'", "$orderby": "Created desc", "$top": str(combien),
        "$select": "ResultKey,Id,PrintJobId,FileName,PdfSize,Created"}).get("value", [])


def dernieres(jeton: str) -> None:
    for ligne in derniers_pdfs(jeton):
        print(f"{ligne['ResultKey']:>8}  {ligne.get('Created')}  {ligne.get('PdfSize'):>8} octets  "
              f"{ligne.get('FileName')}")


def voir(archive: Archive) -> None:
    rapport = archive.rapport()
    if rapport:
        print({k: v for k, v in rapport.items() if not k.startswith("@") and v not in (None, "")})
    else:
        print(f"Aucune ligne ArchiveSet lisible pour la clé {archive.cle}.")
    for ligne in archive.pdfs():
        print({k: v for k, v in ligne.items() if k in ("Id", "FileName", "LayoutName", "PdfSize", "Created")})
    meta, _ = fichiers(archive.cle)
    if meta.exists():
        print("Sauvegarde :", json.loads(meta.read_text(encoding="utf-8")))
    print("Commande :", numero_de_commande(rapport))


def remplacer(archive: Archive, numero: str | None, a_blanc: bool = False) -> None:
    ligne = archive.le_pdf()
    rapport = archive.rapport()
    if rapport and rapport.get("ReportId") != RAPPORT:
        raise EssaiImpossible(f"Rapport {rapport.get('ReportId')} : l'essai ne touche que {RAPPORT}.")
    numero = numero or numero_de_commande(rapport)
    if not numero:
        raise EssaiImpossible("Numéro de commande introuvable dans l'archive : le donner en second argument.")

    # 1. Sauvegarde, avant toute écriture ; la première sauvegarde (d'avant tout essai) n'est jamais écrasée.
    SAUVEGARDES.mkdir(parents=True, exist_ok=True)
    meta, avant = fichiers(archive.cle)
    if a_blanc:
        pass
    elif not meta.exists():
        original = archive.telecharger(ligne["Id"])
        avant.write_bytes(original)
        if empreinte(avant.read_bytes()) != empreinte(original):
            raise EssaiImpossible("La sauvegarde relue ne correspond pas : rien n'est écrit.")
        meta.write_text(json.dumps({
            "cle": archive.cle, "id": ligne["Id"], "fichier": ligne.get("FileName"), "commande": numero,
            "taille": len(original), "sha256": empreinte(original),
            "sauvegarde_le": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Sauvegardé : {avant} ({len(original)} octets)")
    else:
        print(f"Sauvegarde existante gardée : {avant}")

    # 2. Notre PDF, avec le jeton de l'utilisateur (et le compte technique pour la référence, s'il existe).
    utilisateur = archive.lecteur
    generation = generer(utilisateur, compte_technique.lecteur("fr-FR") or utilisateur, numero)
    notre = generation.contenu
    (SAUVEGARDES / f"{archive.cle}_notre.pdf").write_bytes(notre)
    for avertissement in generation.commande.avertissements:
        print("⚠", avertissement)
    print(f"Notre PDF ({numero}) : {len(notre)} octets, {generation.pages} page(s) + annexes, "
          f"lecture {generation.duree_lecture_s} s, rendu {generation.duree_pdf_s} s")
    if a_blanc:
        print(f"À blanc : rien n'est écrit dans l'archive {archive.cle}.")
        return

    # 3. L'écriture, puis la preuve par relecture.
    archive.ecrire(ligne["Id"], ligne["@odata.etag"], notre)
    relu = archive.telecharger(ligne["Id"])
    if empreinte(relu) != empreinte(notre):
        raise EssaiImpossible(f"L'archive rend {len(relu)} octets, pas notre PDF ({len(notre)}) : à examiner, "
                              f"puis restaurer {archive.cle}")
    print(f"✅ L'archive {archive.cle} rend notre PDF. Retour arrière : restaurer {archive.cle}")


def restaurer(archive: Archive) -> None:
    meta, avant = fichiers(archive.cle)
    if not meta.exists():
        raise EssaiImpossible(f"Pas de sauvegarde pour la clé {archive.cle} : rien à restaurer.")
    attendu = json.loads(meta.read_text(encoding="utf-8"))
    original = avant.read_bytes()
    if empreinte(original) != attendu["sha256"]:
        raise EssaiImpossible("La sauvegarde ne correspond plus à son empreinte : rien n'est écrit.")
    ligne = next((l for l in archive.pdfs() if l["Id"] == attendu["id"]), None)
    if ligne is None:
        raise EssaiImpossible(f"Le PDF {attendu['id']} n'est plus dans l'archive {archive.cle} (purgé ?) : "
                              "rien à restaurer.")
    archive.ecrire(ligne["Id"], ligne["@odata.etag"], original)
    relu = archive.telecharger(ligne["Id"])
    if empreinte(relu) != attendu["sha256"]:
        raise EssaiImpossible(f"L'archive {archive.cle} rend {len(relu)} octets, empreinte différente de "
                              "l'original : à examiner.")
    print(f"✅ Restauré : l'archive {archive.cle} rend de nouveau le PDF d'origine ({len(relu)} octets, "
          "même empreinte).")


def ecouter(intervalle_s: float, depuis: str | None, a_blanc: bool) -> None:
    """Chaque nouvelle impression « Armony layout » de l'utilisateur, remplacée dès qu'elle paraît dans l'archive."""
    depuis = depuis or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    traites: set[tuple[int, str]] = set()
    print(f"À l'écoute des impressions de bons de commande créées après {depuis} (UTC), toutes les "
          f"{intervalle_s:g} s{' — À BLANC' if a_blanc else ''}. Ctrl+C pour arrêter.")
    while True:
        try:
            jeton = jeton_utilisateur()
            nouveaux = [l for l in derniers_pdfs(jeton, 10)
                        if l.get("Created", "") > depuis and (l["ResultKey"], l["Id"]) not in traites]
            for ligne in sorted(nouveaux, key=lambda l: l["Created"]):
                traites.add((ligne["ResultKey"], ligne["Id"]))
                print(f"\n{datetime.now():%H:%M:%S}  impression {ligne['ResultKey']} vue (archivée à "
                      f"{ligne['Created']})")
                debut = time.monotonic()
                try:
                    remplacer(Archive(jeton, ligne["ResultKey"]), None, a_blanc)
                    print(f"   traitée en {time.monotonic() - debut:.1f} s")
                except (EssaiImpossible, ErreurIFS) as erreur:
                    print(f"   ⚠️ {erreur}")
        except ErreurIFS as erreur:
            print(f"⚠️ {erreur}")
        time.sleep(intervalle_s)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parametres = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parametres.add_argument("action", choices=["dernieres", "voir", "remplacer", "ecouter", "restaurer"])
    parametres.add_argument("cle", nargs="?", type=int)
    parametres.add_argument("numero", nargs="?")
    parametres.add_argument("--a-blanc", action="store_true", help="tout faire sauf écrire dans l'archive")
    parametres.add_argument("--toutes-les", type=float, default=2.0, help="intervalle d'écoute, en secondes")
    parametres.add_argument("--depuis", help="écouter les impressions archivées après cet instant UTC "
                                             "(AAAA-MM-JJTHH:MM:SSZ), au lieu de maintenant")
    args = parametres.parse_args()
    if args.action in ("voir", "remplacer") and args.cle is None:
        parametres.error("la clé d'archive est requise")

    try:
        if args.action == "dernieres":
            dernieres(jeton_utilisateur())
        elif args.action == "voir":
            voir(Archive(jeton_utilisateur(), args.cle))
        elif args.action == "remplacer":
            remplacer(Archive(jeton_utilisateur(), args.cle), args.numero, args.a_blanc)
        elif args.action == "ecouter":
            ecouter(args.toutes_les, args.depuis, args.a_blanc)
        else:
            cles = [args.cle] if args.cle else sorted(int(p.stem) for p in SAUVEGARDES.glob("*.json"))
            for cle in cles:
                restaurer(Archive(jeton_utilisateur(), cle))
    except EssaiImpossible as erreur:
        sys.exit(str(erreur))
    except KeyboardInterrupt:
        print("\nArrêté.")
    finally:
        pdf.arreter()


if __name__ == "__main__":
    main()
