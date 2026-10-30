---
name: deployer-editiques
description: Livre et déploie ifs-app-editique puis la branche sur l'impression IFS — version, tests, commit et push sur les deux dépôts, déploiement Render (AWS ensuite), vérification de /sante, essai direct de l'aperçu, bascule du paramètre ARMONY_SERVER d'un environnement IFS avec retour arrière, preuve par l'archive IFS et par un HAR du navigateur. À utiliser dès que l'utilisateur parle de livrer, pousser, déployer, mettre en service, basculer ou rebasculer un environnement (CFG, TST, UAT, TRN, PROD), revenir à Armony, ou quand il colle des journaux Render, une erreur de la boîte d'impression ou un fichier .har.
---

# Livrer, déployer et basculer

Trois gestes, **chacun montré avant d'être joué** et jamais dans le même mouvement : livrer une version (code),
la déployer (hébergement), basculer un environnement IFS (configuration). Je ne commite, ne pousse et ne bascule
rien sans le feu vert explicite de l'utilisateur ; un feu vert vaut pour un geste, pas pour le suivant.

## Repères

| | |
|---|---|
| Dépôts | `origin` = `guinetb-globasoft/ifs-editique`, `ga-sa` = `GA-SA/editique-ifs` ; pousser `main` sur **les deux** |
| Hébergement actuel | Render, `https://ifs-app-editique.onrender.com`, déploiement automatique depuis `main` (`render.yaml`) |
| Hébergement cible | AWS, plateforme GA (eu-west-3, ECS Fargate) : page « Éditiques IFS sur AWS » |
| Compte technique | `IFS_TECH_CLIENT_ID=ARMONY_SVC` ; secret saisi par l'utilisateur (`.env`, Render), jamais par moi |
| Aiguillage IFS | paramètre système `ARMONY_SERVER`, un par environnement |
| CFG, valeur d'origine | `https://armony-qua.ga.fr/AxData_Rec`, gardée dans `sorties\armony_server_cfg.json` |
| État au 30/10/2026 | **CFG basculé vers Render**, version 0.3.4 ; aperçu réel prouvé (C105125 en 4 s, C103212 de 97 lignes en 7,4 s) |

## A. Livrer une version

1. Tests hors ligne : `.venv\Scripts\python.exe -m pytest tests -q`, tous verts.
2. Version : `app/version.py` (une version par commit, ligne d'historique).
3. Documentation à jour (CLAUDE.md « État », spec, décisions), puis l'agent **`verif-doc-editiques`**.
4. Commit avec la ligne d'attribution, **après validation** ; push `origin main` puis `ga-sa main`, **après
   validation**. Mon terminal n'est pas interactif : si Git demande des identifiants pour un dépôt neuf
   (`credential.https://github.com.usehttppath true`), l'utilisateur pousse une première fois depuis le sien.

## B. Déployer et vérifier

1. Render redéploie seul depuis `main` ; attendre que `GET /sante` rende la nouvelle `version`, avec
   `compte_technique` et `relais_armony` à `true`. Une seule vérification, pas de boucle d'attente : l'utilisateur
   peut l'interrompre.
2. **Essai direct, sans basculer** : appeler `/GetDownload.aspx?layout_name=ReportPreview.axdata&RESULT_KEY_=<clé>&PRINT_JOB_ID_=<travail>&USER_ID_=<id>`
   sur une impression faite par l'utilisateur (trouver la clé avec `outils\essai_archive.py dernieres`), puis
   vérifier l'archive : `outils\essai_archive.py voir <clé>`. Le PDF déposé porte « ifs-app-editique <version> »
   dans ses propriétés.

## C. Basculer un environnement IFS

1. `outils\armony_server.py voir`, puis `basculer <url>` **après validation** : la valeur d'origine est gardée
   avant la première bascule et chaque écriture est relue. Retour : `retablir`.
2. L'utilisateur prévisualise une pièce dans IFS ; je vérifie l'archive (clé, travail, PDF signé) et, s'il en
   fournit un, le HAR de son navigateur (`ReportDirectPrintRequest`, puis le téléchargement du PDF). **Un HAR
   contient jetons et cookies** : n'en lire que méthode, chemin, statut, durée, taille et corps d'erreur.

## Pièges déjà payés

- **IFS envoie les clés en décimal** (`RESULT_KEY_=56608.0`) : `entier()` dans `app/impression.py`.
- **Le workflow d'aperçu lit la réponse** : renvoyer le XML d'Armony (`<Root><Error>Dummy</Error></Root>`), sinon la
  boîte affiche « PrintDialog/PrintDialog (erreur serveur) » alors que le PDF est déjà dans l'archive.
- **Le workflow d'aperçu tourne aussi sur OK** : un OK appelle `GetDownload.aspx`, puis `Execute.aspx`.
- **Horodatages IFS** : `CreatedTime` et `Created` sont en heure de Paris marquée `Z` ; le HAR et l'erreur de la boîte
  sont en UTC.
- **`PdfSize` ne change pas** quand on remplace le PDF archivé (même constat avec Armony) ; vérifier par
  téléchargement et propriétés du PDF.
- **L'archive est cloisonnée par utilisateur** : le jeton de l'utilisateur ne voit que ses impressions ; le compte
  technique voit tout.
- **Sur CFG, Armony ne produit pas le bon de commande** : la page d'attente « Armony Report » reste ; ce n'est pas
  notre panne.
- Les appels d'IFS arrivent de `20.61.209.19` (observé sur CFG) ; pas de filtrage par IP décidé (D-009).
