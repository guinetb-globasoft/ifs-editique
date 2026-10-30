# Éditiques IFS — sans Armony

Application FastAPI qui produit les éditiques d'IFS Cloud (PDF) à la place d'Armony (Ootary) : elle lit IFS, met en
page en HTML, Chromium rend le PDF. Elle **prend la place d'Armony dans l'impression IFS** (D-008, D-009) : IFS
l'appelle aux mêmes adresses qu'Armony dès que le paramètre système `ARMONY_SERVER` pointe vers elle. Le bouton
d'aperçu (`/commande-achat/<n°>`) existe encore : il est à retirer (D-011).

- Logiciel : [README.md](README.md). Spec du bon de commande : [docs/specs/commande-achat.md](docs/specs/commande-achat.md).
  Décisions : [docs/decisions.md](docs/decisions.md).
- Cahier des charges de chaque éditique : le projet Armony dans `..\armony-projects` (une branche par environnement ;
  `PROD-PROD` fait foi). Armony n'est **jamais** une dépendance de l'application.
- Dépôts : `origin` = `guinetb-globasoft/ifs-editique`, `ga-sa` = `GA-SA/editique-ifs` (pousser `main` sur les deux).
  Hébergé sur Render (`render.yaml`), cible AWS sur la plateforme GA.

## Skills et agents du projet

| | Quand |
|---|---|
| skill `reprendre-editique` | reprendre une éditique Armony : règles, spec, lecture IFS, gabarit, calage, essai réel |
| skill `deployer-editiques` | livrer, déployer, basculer ou rétablir `ARMONY_SERVER`, lire un journal Render ou un HAR |
| agent `verif-mise-en-page` | mesurer un PDF contre celui d'Armony, à la ligne de base, avant tout chiffre de fidélité |
| agent `verif-doc-editiques` | vérifier que la doc dit ce que fait le code, avant chaque livraison |

## Commandes

```powershell
.\demarrer.ps1 -Rechargement                       # venv, dépendances, Chromium, serveur
.\.venv\Scripts\python.exe -m pytest tests -q      # hors ligne
.\.venv\Scripts\python.exe outils\apercu.py        # PDF sans IFS -> sorties\
.\.venv\Scripts\python.exe outils\mesurer_mise_en_page.py <notre.pdf> <armony.pdf>   # requirements-dev.txt
.\.venv\Scripts\python.exe outils\armony_server.py voir|basculer <url>|retablir      # aiguillage IFS
.\.venv\Scripts\python.exe outils\essai_archive.py dernieres|voir|remplacer|restaurer
```

## État au 30/10/2026 — version 0.3.4

- ⚠️ **CFG est BASCULÉ** vers Render (`ARMONY_SERVER` = `https://ifs-app-editique.onrender.com`). Retour à Armony :
  `outils\armony_server.py retablir` (valeur d'origine `https://armony-qua.ga.fr/AxData_Rec`, gardée dans
  `sorties\armony_server_cfg.json`).
- ✅ **Aperçu réel prouvé sur CFG** : C105125 (8 lignes) en 4 s ; C103212 (97 lignes, la plus grosse de CFG) en 7,4 s
  du clic au PDF (HAR du 29/10), sans erreur depuis la 0.3.2.
- ✅ OK : la suite d'Armony a tourné une fois en réel (travail recréé, PDF déposé, archive « imprimée », clé 56611).
  **E-mail non envoyé** : pas de SMTP (spec Q13 ; expéditeur `@ga.fr` décidé).
- Compte technique : `ARMONY_SVC` (droits d'Armony). Un client propre, un par realm, est décidé (D-011) : à créer
  par l'admin IFS.
- **Décisions DSI du 30/10 (D-011)** : bouton d'aperçu à retirer, avec la connexion des utilisateurs ; destinataires,
  copies et copies cachées lus dans IFS, SMTP d'Armony non repris ; pas d'impression papier ; une centaine
  d'impressions par jour au plus ; projet de 3 j de dev et 2 j de recette, sans cohabitation : le renvoi à Armony ne
  va pas en PROD. Réponses détaillées : https://claude.ai/artifact/Y3BD7oXCfZEVYyKtAW7Yud.
- ⚠️ **Mise en page** : tous les textes du bon sont à moins de 1 mm d'Armony **à la ligne de base**, 15 sur 53 sous
  0,3 mm ; le recalage par famille de textes reste à faire (D-010). L'ancien « < 0,3 mm » mesurait le haut des boîtes.
- ⚠️ Mentions et pied de page lus dans `ressources/textes/<société>.json` : **seule GAE** ; une autre société (ex. PQF)
  sort sans mentions légales.
- ⚠️ Contact de livraison du projet : `ProjectDefinitionHandling` répond 403 au compte d'Armony ; lire la même source
  qu'Armony.
- Archive 56607 de BENGUI encore remplacée par notre PDF : `outils\essai_archive.py restaurer 56607`.
- Restent à reprendre : Situation, Certificat, Facture instantanée, Fiche RAC (pas un rapport IFS : lancée chaque
  semaine par un planificateur, D-011), et la disposition « modules » (`MODULE_REP`) vue dans l'aiguillage de CFG.
- Présentations : deck de l'équipe https://claude.ai/artifact/58ANspGFg3tSrni34gqW7w, deck directeur
  https://claude.ai/artifact/NNbpXrK74iUFRcPU34ixeZ, cible AWS https://claude.ai/artifact/Q2kwhMRcrEXDLkQUQWo4RG.

## Invariants

- **Écritures IFS : seulement celles d'Armony**, et seulement par `app/ifs/ecriture.py` (PDF de l'archive, suppression
  du travail reçu, événements `ARMONY_REPORT_JOB` / `ARMONY_REPORT_PRINT`). `app/ifs/lecture.py` n'a que des GET ;
  le bouton d'aperçu n'écrit rien (D-002).
- **Ne jamais deviner un nom IFS.** Le vérifier dans le catalogue (`..\mcp-ifs\data\catalogue-cfg.sqlite`, tables
  `champs`, `entites`, `navigations`, `droits`), dans une requête Armony ou en réel, et dire dans la spec lequel.
- **Énumérations filtrées après lecture**, jamais dans `$filter` ; les filtres passent par `LecteurIFS` (espaces en
  `%20` : IFS refuse « + »).
- **Identité** : impression = compte technique, IFS ayant contrôlé l'accès (D-008) ; le bouton (jeton de
  l'utilisateur, D-003) est à retirer (D-011). Une source de référence illisible n'arrête pas le document :
  avertissement, champ vide.
- **Reproduire ce qu'Armony imprime**, pas ce que son script semble vouloir ; noter l'écart dans la spec. Répondre à
  IFS exactement comme Armony (XML `response_armony.xml`).
- **Mise en page** : toute retouche se mesure contre la référence **à la ligne de base**
  (`outils\mesurer_mise_en_page.py`, agent `verif-mise-en-page`), jamais à l'œil ni sur le haut des boîtes. Ne pas
  réactiver le crénage ni retirer la neutralisation du retrait des gabarits Chromium (D-005, D-010).
- Le jeu `exemples/` est **reconstitué** (coordinateur fictif) : pas de donnée personnelle réelle dans le dépôt.
  Les PDF produits vont dans `sorties/`, hors dépôt. Un HAR contient jetons et cookies : ne jamais en afficher.

## Conventions

- Code, docs et messages en français ; noms IFS tels qu'IFS les écrit.
- Une version par commit (`app/version.py`). Commit, push et bascule seulement sur feu vert de Benoit.
- Ne pas annoncer qu'une chose fonctionne sans l'avoir exécutée, et dire si c'était hors ligne ou en réel.
