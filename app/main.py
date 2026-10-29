"""Routes de l'application.

    GET /commande-achat/{n°}           le PDF, ouvert dans le navigateur
    GET /commande-achat/{n°}/donnees   ce qui a été lu dans IFS, et ce qui manque
    GET /generations                   le temps de chaque génération (?format=json)
    GET /                              saisie d'un numéro, état de la connexion
    GET /sante                         version et instance IFS, sans session
    /GetDownload.aspx, /Execute.aspx   l'impression IFS, aux adresses d'Armony (impression.py, D-008)

Le bouton IFS ouvre `/commande-achat/<n°>` dans un nouvel onglet ; sans jeton,
l'utilisateur passe par le realm IFS (où il est déjà connecté) et revient.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from . import generations
from .config import config
from .impression import routeur as routeur_impression
from .editiques import commande_achat
from .editiques.commande_achat.donnees import CommandeIntrouvable
from .ifs import compte_technique
from .ifs.lecture import Appel, ErreurIFS, LecteurIFS
from .ifs.sso import routeur as routeur_sso
from .ifs.sso import boucle_probable, jeton_de_la_requete, utilisateur_connecte, utilisateur_du_jeton
from .rendu import pdf
from .version import VERSION

journal = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def cycle_de_vie(_app: FastAPI):
    # Chromium démarre avec le serveur, sans le retarder : le premier clic n'attend pas son lancement.
    pdf.demarrer()
    yield
    pdf.arreter()


app = FastAPI(title="Éditiques IFS", version=VERSION, lifespan=cycle_de_vie)
app.add_middleware(SessionMiddleware, secret_key=config.secret_session,
                   session_cookie="editique_session", same_site="lax",
                   https_only=config.ifs_oidc_redirect_uri.startswith("https://"))
app.include_router(routeur_sso)
app.include_router(routeur_impression)


def _lecteurs(request: Request) -> tuple[LecteurIFS, LecteurIFS] | Response:
    """(lecteur utilisateur, lecteur de référence), ou la réponse qui mène au login."""
    jeton = jeton_de_la_requete(request)
    if not jeton:
        if "text/html" in request.headers.get("accept", ""):
            retour = quote(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
            diagnostic = boucle_probable(request)
            if diagnostic is not None:
                # Revenir du realm sans jeton utilisable : y retourner bouclerait sans fin.
                return HTMLResponse(
                    f"<p>Le realm IFS vient de vous authentifier, mais la session n'a pas pu "
                    f"s'ouvrir : {escape(diagnostic)}.</p><p>Détail : <a href='/auth/ifs/statut'>"
                    f"/auth/ifs/statut</a> · <a href='/auth/ifs/login?retour={retour}'>réessayer</a></p>",
                    status_code=500)
            return RedirectResponse(f"/auth/ifs/login?retour={retour}")
        return JSONResponse({"erreur": "Jeton IFS requis (Authorization: Bearer …)."}, status_code=401)
    langue = f"{config.langue}-FR" if config.langue == "fr" else config.langue
    utilisateur = LecteurIFS(jeton=jeton, langue=langue)
    try:
        technique = compte_technique.lecteur(langue)
    except ErreurIFS:
        technique = None  # signalé dans /donnees : les champs concernés seront vides
    return utilisateur, technique or utilisateur


def _appels(utilisateur: LecteurIFS, reference: LecteurIFS) -> list[Appel]:
    return utilisateur.journal + (reference.journal if reference is not utilisateur else [])


@app.get("/commande-achat/{numero}")
def commande_achat_pdf(numero: str, request: Request, telecharger: bool = False):
    lecteurs = _lecteurs(request)
    if isinstance(lecteurs, Response):
        return lecteurs
    debut = time.monotonic()
    entree = {"horodatage": generations.maintenant(), "editique": "commande-achat",
              "numero": numero.strip().upper(),
              "utilisateur": utilisateur_du_jeton(getattr(lecteurs[0], "jeton", "")),
              "instance_ifs": config.instance_ifs, "version": VERSION,
              "compte_technique": lecteurs[1] is not lecteurs[0]}
    reponse: Response
    try:
        generation = commande_achat.generer(*lecteurs, numero, config.langue)
    except CommandeIntrouvable as err:
        entree.update(statut="introuvable", erreur=str(err))
        reponse = HTMLResponse(f"<p>{escape(str(err))}</p>", status_code=404)
    except ErreurIFS as err:
        entree.update(statut="erreur", erreur=str(err))
        reponse = HTMLResponse(f"<p>Lecture IFS impossible : {escape(str(err))}</p>", status_code=502)
    else:
        commande = generation.commande
        entree.update(statut="ok", duree_lecture_ifs_s=generation.duree_lecture_s,
                      duree_pdf_s=generation.duree_pdf_s, pages=generation.pages,
                      lignes=len(commande.lignes), annexes=len(commande.annexes),
                      avertissements=len(commande.avertissements))
        disposition = "attachment" if telecharger else "inline"
        reponse = Response(generation.contenu, media_type="application/pdf", headers={
            "Content-Disposition": f'{disposition}; filename="Commande_{commande.numero}.pdf"',
            "X-Editique-Avertissements": str(len(commande.avertissements)),
            # Visible dans l'onglet Réseau des outils de développement du navigateur.
            "Server-Timing": f"ifs;dur={generation.duree_lecture_s * 1000:.0f};desc=\"Lecture IFS\", "
                             f"pdf;dur={generation.duree_pdf_s * 1000:.0f};desc=\"Rendu PDF\"",
        })

    appels = _appels(*lecteurs)
    plus_lent = max(appels, key=lambda a: a.duree_ms, default=None)
    entree.update(duree_totale_s=round(time.monotonic() - debut, 3), appels_ifs=len(appels),
                  appel_le_plus_lent=None if plus_lent is None else
                  {"chemin": plus_lent.chemin, "duree_ms": plus_lent.duree_ms})
    generations.consigner(entree)
    journal.info("%s %s en %.1f s (IFS %.1f s, %d appels ; PDF %.1f s)%s", entree["numero"],
                 entree["statut"], entree["duree_totale_s"], entree.get("duree_lecture_ifs_s", 0),
                 len(appels), entree.get("duree_pdf_s", 0),
                 f" — appel le plus lent : {plus_lent.chemin} {plus_lent.duree_ms} ms" if plus_lent else "")
    return reponse


@app.get("/commande-achat/{numero}/donnees")
def commande_achat_donnees(numero: str, request: Request):
    lecteurs = _lecteurs(request)
    if isinstance(lecteurs, Response):
        return lecteurs
    utilisateur, reference = lecteurs
    try:
        commande = commande_achat.lire_commande(utilisateur, reference, numero, config.langue)
    except CommandeIntrouvable as err:
        return JSONResponse({"erreur": str(err)}, status_code=404)
    except ErreurIFS as err:
        return JSONResponse({"erreur": str(err)}, status_code=502)
    appels = _appels(utilisateur, reference)
    return JSONResponse({
        "version": VERSION,
        "instance_ifs": config.instance_ifs,
        "compte_technique": compte_technique.configure() and reference is not utilisateur,
        "commande": commande.en_dict(),
        "appels_ifs": [a.en_dict() for a in appels],
    }, headers={"Cache-Control": "no-store"})


@app.get("/generations")
def liste_generations(request: Request, format: str = "html", limite: int = 500):
    """Le temps de chaque génération, la plus récente d'abord. Réservé aux utilisateurs IFS."""
    lecteurs = _lecteurs(request)
    if isinstance(lecteurs, Response):
        return lecteurs
    entrees = generations.lire(limite)
    stats = generations.statistiques(entrees)
    if format == "json":
        return JSONResponse({"statistiques": stats, "generations": entrees},
                            headers={"Cache-Control": "no-store"})

    def s(valeur) -> str:
        return "" if valeur is None else f"{valeur:.1f}".replace(".", ",")

    lignes = "".join(
        f"<tr class='{escape(e.get('statut', ''))}'><td>{escape(e.get('horodatage', '')[:19].replace('T', ' '))}</td>"
        f"<td>{escape(e.get('numero', ''))}</td><td>{escape(e.get('utilisateur', ''))}</td>"
        f"<td>{escape(e.get('instance_ifs', ''))}</td><td>{escape(e.get('statut', ''))}</td>"
        f"<td class='n'><b>{s(e.get('duree_totale_s'))}</b></td><td class='n'>{s(e.get('duree_lecture_ifs_s'))}</td>"
        f"<td class='n'>{s(e.get('duree_pdf_s'))}</td><td class='n'>{e.get('appels_ifs', '')}</td>"
        f"<td>{escape((e.get('appel_le_plus_lent') or {}).get('chemin', ''))} "
        f"{(e.get('appel_le_plus_lent') or {}).get('duree_ms', '')}{' ms' if e.get('appel_le_plus_lent') else ''}</td>"
        f"<td class='n'>{e.get('pages', '')}</td><td class='n'>{e.get('lignes', '')}</td>"
        f"<td class='n'>{e.get('avertissements', '')}</td></tr>"
        for e in entrees)
    resume = (f"{stats['reussies']} générations réussies · médiane {s(stats['mediane_s'])} s · "
              f"moyenne {s(stats['moyenne_s'])} s · max {s(stats['max_s'])} s"
              if stats.get("reussies") else "Aucune génération réussie pour l'instant.")
    return HTMLResponse(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Générations</title>
<style>body{{font-family:Calibri,sans-serif;margin:2rem;font-size:14px}}
table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:.2rem .5rem;text-align:left}}
th{{background:#ec007e;color:#fff}}td.n{{text-align:right}}tr.erreur,tr.introuvable{{color:#a00}}</style>
</head><body><h1>Générations</h1><p>{resume} · <a href="?format=json">JSON</a></p>
<table><tr><th>Quand</th><th>N°</th><th>Qui</th><th>IFS</th><th>Statut</th><th>Total (s)</th>
<th>Lecture IFS (s)</th><th>PDF (s)</th><th>Appels IFS</th><th>Appel le plus lent</th><th>Pages</th>
<th>Lignes</th><th>Avert.</th></tr>{lignes}</table></body></html>""")


@app.get("/sante")
def sante():
    return {"version": VERSION, "instance_ifs": config.instance_ifs,
            "compte_technique": compte_technique.configure(), "relais_armony": bool(config.armony_relais)}


@app.get("/", response_class=HTMLResponse)
def accueil(request: Request):
    qui = utilisateur_connecte(request)
    connexion = (f"Connecté à IFS {escape(config.instance_ifs)} : <b>{escape(qui)}</b> · "
                 f"<a href='/auth/ifs/deconnexion'>se déconnecter</a>" if qui
                 else f"IFS {escape(config.instance_ifs)} : vous serez connecté au premier document.")
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Éditiques IFS</title>
<style>body{{font-family:Calibri,sans-serif;margin:3rem auto;max-width:36rem;padding:0 1rem}}
input,button{{font-size:1rem;padding:.4rem}}small{{color:#666}}</style></head><body>
<h1>Éditiques IFS</h1>
<form onsubmit="window.open('/commande-achat/'+encodeURIComponent(this.n.value.trim()));return false">
<label>Bon de commande n° <input name="n" placeholder="C106553" required autofocus></label>
<button>Générer</button></form>
<p><small>{connexion}</small></p>
<p><small><a href="/generations">Temps de génération</a> · Version {VERSION}</small></p></body></html>"""
