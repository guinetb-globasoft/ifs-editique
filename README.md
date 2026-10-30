# Éditiques IFS

Produire les éditiques d'IFS Cloud **sans Armony** : l'application lit le document dans IFS, le met en page et rend
le PDF. Première éditique : **le bon de commande** (commande d'achat), à l'image du projet Armony `Commande_dachat v1`.

L'application prend la place d'Armony dans l'impression IFS (aperçu, OK, e-mail depuis la boîte d'impression) : rien
ne change pour l'utilisateur (spec § 5, D-008, D-009). C'est en service sur CFG ; l'e-mail n'est pas encore envoyé
(pas de SMTP). Le bouton d'aperçu construit en premier est à retirer (D-011).

> Spécification du bon de commande : [docs/specs/commande-achat.md](docs/specs/commande-achat.md).
> Décisions : [docs/decisions.md](docs/decisions.md).

## Lancer en local

```powershell
.\demarrer.ps1                 # http://localhost:8000
.\demarrer.ps1 -Rechargement   # redémarre à chaque modification du code
```

Le script crée le venv, installe les dépendances et le Chromium de Playwright, copie `.env.example` en `.env`.
Renseigner ensuite le client Keycloak (`IFS_CLIENT_ID`, `IFS_CLIENT_SECRET`) : en local sur CFG, le client `POCs`
déclare déjà l'URI de retour `http://localhost:8000/auth/ifs/callback/`.

**Sans IFS**, un aperçu se produit depuis des réponses enregistrées :

```powershell
.\.venv\Scripts\python.exe outils\apercu.py          # -> sorties\Commande_C106553.pdf
.\.venv\Scripts\python.exe outils\apercu.py --html   # le HTML seul, pour régler la mise en page
```

**Essai sur CFG** de l'étape clé du branchement (D-008) : mettre notre PDF à la place de celui d'Armony dans
l'archive d'une impression qu'on vient de faire, puis remettre l'original, vérifié octet pour octet :

```powershell
.\.venv\Scripts\python.exe outils\essai_archive.py dernieres             # mes dernières impressions de BDC
.\.venv\Scripts\python.exe outils\essai_archive.py remplacer <clé> <n°>  # sauvegarde, puis notre PDF
.\.venv\Scripts\python.exe outils\essai_archive.py restaurer <clé>       # retour arrière
```

## Brancher sur l'impression IFS (Render)

L'application répond aux adresses d'Armony (`/GetDownload.aspx` pour l'aperçu, `/Execute.aspx` pour OK) ; IFS
l'appelle dès que le paramètre système `ARMONY_SERVER` pointe vers elle (D-009). Le reste est relayé à Armony, pendant
les essais seulement : ce renvoi ne va pas en PROD (D-011).

1. Render : nouveau *Blueprint* depuis le dépôt (`render.yaml`), puis saisir `IFS_TECH_CLIENT_SECRET` (client
   `ARMONY_SVC`). Vérifier `https://<service>.onrender.com/sante` : `compte_technique` et `relais_armony` à `true`.
2. Basculer, essayer une prévisualisation de bon de commande dans IFS, puis rétablir :

```powershell
.\.venv\Scripts\python.exe outils\armony_server.py basculer https://<service>.onrender.com
.\.venv\Scripts\python.exe outils\armony_server.py retablir
```

Chaque impression traitée est consignée (journal Render, et `/generations` en local).

## Les routes

| Route | Rôle |
|---|---|
| `GET /commande-achat/{n°}` | le PDF (bon de commande puis CGA), affiché dans le navigateur ; `?telecharger=1` pour le télécharger |
| `GET /commande-achat/{n°}/donnees` | ce qui a été lu dans IFS, chaque appel et son statut, les avertissements |
| `GET /generations` | le temps de chaque génération (total, lecture IFS, PDF, appel IFS le plus lent), médiane et maximum ; `?format=json` |
| `GET /auth/ifs/statut` | l'état de la session IFS (client, expiration du jeton), sans aucun jeton |
| `GET /` | saisie d'un numéro, état de la connexion IFS |
| `GET /sante` | version, instance IFS, compte technique configuré ou non |

Un navigateur sans session est renvoyé au realm IFS, puis revient. Un autre programme présente son jeton IFS dans
`Authorization: Bearer …`.

## Le bouton d'aperçu dans IFS (à retirer)

Dans Page Designer, sur l'écran **Commande d'achat** : ajouter une commande personnalisée qui ouvre, dans un nouvel
onglet, `https://<hôte>/commande-achat/${OrderNo}`. C'est un aperçu, sans effet dans IFS. Décision du 30/10/2026 :
l'aperçu passe par la boîte d'impression d'IFS, le bouton est retiré avec la connexion des utilisateurs (D-011).

## Temps de génération

Chaque demande de PDF, réussie ou non, ajoute une ligne à `data/generations.jsonl` (hors dépôt) : quand, qui, quelle
commande, temps total, lecture IFS, rendu PDF, nombre d'appels IFS et le plus lent. La même ligne s'affiche dans la
console du serveur, et la réponse PDF porte un en-tête `Server-Timing` (onglet Réseau du navigateur).

Ce qui a été fait pour la vitesse (0.2.0) : les lectures IFS partent en parallèle une fois l'en-tête lu, les textes
document se lisent en une requête pour toute la commande, et Chromium reste ouvert (le lancer coûtait 3,7 s par PDF).

## Identité et droits

- Dans l'**impression IFS**, IFS a contrôlé l'accès : tout est lu avec le compte technique (D-008). Les deux points
  suivants valent pour le bouton, à retirer (D-011).
- La **commande** est lue avec le jeton de l'utilisateur, sur `PurchaseOrderHandling` : ce qu'il ne voit pas dans IFS,
  il ne l'imprime pas.
- Les **données de référence** (SIRET, logo, phrases, CGA, coordonnées) viennent de projections qu'un acheteur n'ouvre
  pas. Elles sont lues avec un compte technique (`IFS_TECH_CLIENT_ID` / `IFS_TECH_CLIENT_SECRET`, client Keycloak avec
  utilisateur de service) s'il est configuré, sinon avec l'utilisateur : un administrateur obtient alors un document
  complet, un acheteur un document dont `/donnees` liste les manques.
- Le circuit d'impression écrit ce qu'Armony écrit, et rien d'autre, par `app/ifs/ecriture.py` seulement : PDF de
  l'archive, travail d'impression, état « imprimé ». Le bouton n'écrit rien.

## Structure

```
app/
├── config.py              .env -> configuration
├── main.py                routes
├── impression.py          les adresses d'Armony appelées par IFS (aperçu, OK), le renvoi à Armony
├── version.py             la version, en un seul endroit
├── ifs/
│   ├── lecture.py         lecture OData (GET seulement), journal des appels
│   ├── ecriture.py        les seules écritures, celles d'Armony
│   ├── sso.py             login IFS : OIDC authorization code + PKCE, jetons en mémoire
│   ├── compte_technique.py  client_credentials, facultatif
│   └── enregistre.py      réponses IFS rejouées (tests, aperçu)
├── rendu/
│   ├── formats.py         nombres et dates à la française
│   └── pdf.py             HTML -> PDF (Chromium), concaténation des annexes
└── editiques/commande_achat/
    ├── donnees.py         IFS -> CommandeAchat : toutes les règles de la spec
    ├── modele.py          la forme du document
    ├── mise_en_page.py    CommandeAchat -> HTML, en-tête, pied
    └── gabarit/           document.html.j2, entete/pied.html.j2, style.css, libelles.json
ressources/                logo de repli, textes provisoires par société (mentions, pied de page)
exemples/                  réponses IFS reconstituées de C106553
outils/                    apercu.py (un PDF sans IFS), armony_server.py (aiguillage), essai_archive.py,
                           mesurer_mise_en_page.py (fidélité à la ligne de base)
tests/                     hors ligne : règles, mise en page, API, SSO
docs/                      spec et décisions
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Hors ligne : ni IFS ni realm. Ceux qui produisent un PDF demandent le Chromium de Playwright et sautent sans lui.

## Ajouter une éditique

Un dossier `app/editiques/<nom>/` sur le modèle de `commande_achat` (données, modèle, gabarit), une route dans
`main.py`, une spec dans `docs/specs/`. Le projet Armony correspondant est dans `armony-projects` (branche de
l'environnement) : il sert de cahier des charges, pas de dépendance.
