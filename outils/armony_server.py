"""Brancher ou débrancher l'application sur l'impression IFS : le paramètre système `ARMONY_SERVER` (D-008, spec § 5.2).

    .venv\\Scripts\\python.exe outils\\armony_server.py voir
    .venv\\Scripts\\python.exe outils\\armony_server.py basculer https://<application>   # sauvegarde, puis bascule
    .venv\\Scripts\\python.exe outils\\armony_server.py retablir                         # remet la valeur d'origine

Une seule valeur change dans IFS. Avant la première bascule, la valeur d'origine est gardée dans
`sorties/armony_server_<instance>.json` (hors dépôt) et n'est jamais écrasée ensuite ; `retablir` la remet. Chaque
écriture est relue. Même chemin que l'écran Paramètres système d'IFS : l'entité virtuelle `ModifySystemParamVirtual`
puis son action `SaveChanges`, avec le jeton de l'utilisateur (outil de développement de mcp-ifs, comme
`essai_archive.py`).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "outils"))

from app.config import config  # noqa: E402
from essai_archive import jeton_utilisateur  # noqa: E402

PARAMETRE = "ARMONY_SERVER"
P = f"{config.url_projection}/FndSettings.svc"
SAUVEGARDE = RACINE / "sorties" / f"armony_server_{config.instance_ifs.lower()}.json"


def _entetes(jeton: str, **autres) -> dict[str, str]:
    return {"Authorization": f"Bearer {jeton}", "Accept": "application/json", "Accept-Language": "fr-FR", **autres}


def lire(jeton: str) -> dict:
    reponse = requests.get(f"{P}/FndSettingsSet(Parameter='{PARAMETRE}')", headers=_entetes(jeton), timeout=60)
    if not reponse.ok:
        sys.exit(f"Lecture de {PARAMETRE} impossible : {reponse.status_code} {reponse.text[:300]}")
    return reponse.json()


def ecrire(jeton: str, valeur: str) -> None:
    actuel = lire(jeton)
    virtuel = requests.post(f"{P}/ModifySystemParamVirtualSet", headers=_entetes(jeton), timeout=60, json={
        "Parameter": PARAMETRE, "ParameterName": actuel.get("ParameterDesc"), "ParameterValue": valeur,
        "OriginalValue": actuel.get("Value"), "ValueType": actuel.get("ValueType"), "Domain": actuel.get("Domain"),
        "DomainDesc": actuel.get("DomainDesc"), "ClientReadOnly": bool(actuel.get("ClientReadOnly")),
        "IsValuesList": False})
    if not virtuel.ok:
        sys.exit(f"IFS refuse la saisie : {virtuel.status_code} {virtuel.text[:400]}")
    objet = virtuel.json()
    enregistrer = requests.post(
        f"{P}/ModifySystemParamVirtualSet(Objkey='{objet['Objkey']}')/IfsApp.FndSettings.ModifySystemParamVirtual_SaveChanges",
        headers=_entetes(jeton, **{"If-Match": objet.get("@odata.etag", "*")}), json={}, timeout=60)
    if not enregistrer.ok:
        sys.exit(f"IFS refuse l'enregistrement : {enregistrer.status_code} {enregistrer.text[:400]}")
    relu = lire(jeton).get("Value")
    if relu != valeur:
        sys.exit(f"⚠️ Relu : {relu!r}, attendu {valeur!r}.")
    print(f"✅ {PARAMETRE} = {relu} (IFS {config.instance_ifs})")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parametres = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parametres.add_argument("action", choices=["voir", "basculer", "retablir"])
    parametres.add_argument("url", nargs="?")
    args = parametres.parse_args()
    jeton = jeton_utilisateur()

    if args.action == "voir":
        print(f"{PARAMETRE} = {lire(jeton).get('Value')} (IFS {config.instance_ifs})")
        if SAUVEGARDE.exists():
            print("Valeur d'origine gardée :", json.loads(SAUVEGARDE.read_text(encoding="utf-8"))["valeur"])
    elif args.action == "basculer":
        if not args.url:
            parametres.error("l'URL de l'application est requise")
        if not SAUVEGARDE.exists():
            SAUVEGARDE.parent.mkdir(parents=True, exist_ok=True)
            SAUVEGARDE.write_text(json.dumps({"parametre": PARAMETRE, "instance": config.instance_ifs,
                                              "valeur": lire(jeton).get("Value"),
                                              "sauvegarde_le": datetime.now().isoformat(timespec="seconds")},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
        print("Valeur d'origine gardée :", json.loads(SAUVEGARDE.read_text(encoding="utf-8"))["valeur"])
        ecrire(jeton, args.url.rstrip("/"))
    else:
        if not SAUVEGARDE.exists():
            sys.exit(f"Pas de valeur d'origine gardée ({SAUVEGARDE}) : rien à rétablir.")
        ecrire(jeton, json.loads(SAUVEGARDE.read_text(encoding="utf-8"))["valeur"])


if __name__ == "__main__":
    main()
