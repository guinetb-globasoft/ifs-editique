---
name: reprendre-editique
description: Reprend une éditique Armony dans l'application ifs-app-editique — lire le projet Armony (règles, cas particuliers, pas seulement le visuel), écrire la spec, coder la lecture IFS et le gabarit, caler la mise en page par la ligne de base contre le PDF Armony, tester hors ligne puis en réel sur CFG, et la brancher sur l'impression IFS. À utiliser dès que l'utilisateur parle de reprendre, refaire ou migrer une éditique (Situation, Certificat, Facture instantanée, Fiche RAC, modules, ou une nouvelle), d'ajouter une règle d'Armony, de corriger un écart de contenu ou de mise en page avec Armony, ou de « faire la suivante ».
---

# Reprendre une éditique Armony

Le bon de commande (`app/editiques/commande_achat/`, spec `docs/specs/commande-achat.md`) est le modèle : chaque
nouvelle éditique en suit la structure. On ne part **ni d'une page blanche, ni du seul visuel** : la logique métier
d'Armony est relue et reprise, puis consignée.

## Repères

| | |
|---|---|
| Projets Armony | `..\armony-projects`, une branche par environnement ; **`PROD-PROD` fait foi** (`git show origin/PROD-PROD:projets/<Projet>/<fichier>.xml`) |
| Connecteurs Armony | `scripts/ReportOk.axdata` (PROD-PROD) ; `ReportPreview.axdata` relevé dans la spec du bon (§ 5.2) |
| Aiguillage dans IFS | `CustomProjectionArmonyLayoutConfig.svc/ArmonyLayoutConfigSet` : rapport + disposition → fichier Armony |
| Catalogue des noms IFS | `..\mcp-ifs\data\catalogue-cfg.sqlite` (tables `champs`, `entites`, `navigations`, `droits`) |
| Lectures en réel | jeton utilisateur par `..\mcp-ifs\outils\jeton.py` (navigateur), ou compte technique `ARMONY_SVC` du `.env` |
| PDF Armony de référence | `..\tests-automatisés-IFS\outputs\editiques\` (ou une impression archivée, voir `outils\essai_archive.py`) |
| Traductions | `..\armony-projects\ressources\Ressources GA\Traduction_GA_*.xlsx` |

Éditiques gérées par Armony sur CFG (29/10/2026) : `PURCHASE_ORDER_PRINT_REP` (fait), `APP_FOR_PAYMENT_REP`
(Situation), `SUBVAL_VALUATION_REP` (Certificat), `INSTANT_INVOICE_REP` (Facture instantanée), `MODULE_REP`
(« Infos composant »). La Fiche RAC n'est pas un rapport IFS : elle sera lancée automatiquement chaque semaine
(D-011) ; établir d'abord ses destinataires (probablement `GaRacMailingList`) et sa période.

## Méthode

1. **Lire le projet Armony** : requêtes (`DataBaseQuery`), éléments et leurs scripts (`XmlValue`, conditions),
   éléments **désactivés**, toile de page (Fabric.js), traductions. Relever chaque règle, chaque cas particulier.
   Comparer les branches d'environnement pour savoir quelle version est branchée.
2. **Écrire la spec** `docs/specs/<éditique>.md` sur le modèle du bon : règles `RG-nn`, sources avec leur colonne
   « Vérifié » (**catalogue**, **Armony** ou **réel**), cas à recetter, écarts connus, questions ouvertes. Reproduire
   **ce qu'Armony imprime**, pas ce que son script semble vouloir, et noter l'écart.
3. **Lecture IFS** (`donnees.py`) : uniquement des GET, par `LecteurIFS`. Chaque nom vérifié dans le catalogue
   avant usage. Énumérations filtrées **après** lecture, jamais dans `$filter`. Lectures parallèles une fois
   l'en-tête lu. Une donnée de référence illisible donne un avertissement, pas une erreur.
4. **Gabarit** (`gabarit/` : Jinja2 + CSS), libellés depuis le fichier de traduction d'Armony.
5. **Jeu d'exemple reconstitué** dans `exemples/` (aucune donnée personnelle réelle) et **tests hors ligne**
   (`tests/`), dont un par cas particulier de la spec.
6. **Caler la mise en page** contre le PDF Armony de la même pièce, avec
   `outils\mesurer_mise_en_page.py <notre.pdf> <armony.pdf>`, puis l'agent **`verif-mise-en-page`**.
7. **Essai en réel** sur CFG, en lecture seule : générer quelques pièces réelles, dont la plus grosse
   (`$apply=groupby((…),aggregate($count as Lignes))` fonctionne sur IFS), lire les avertissements.
8. **Brancher sur l'impression** : `app/impression.py` choisit l'éditique d'après le `ReportId` de l'archive ; ajouter
   la nouvelle à cet aiguillage, avec ses tests dans `tests/test_impression.py`. Puis la skill
   **`deployer-editiques`**.
9. Lancer l'agent **`verif-doc-editiques`** avant de livrer.

## Pièges déjà payés

- **Mesurer à la ligne de base, jamais sur le haut des boîtes de texte.** Les deux moteurs PDF ne déclarent pas la
  même hauteur de police : la mesure par boîte a fait annoncer « < 0,3 mm » alors que les textes étaient jusqu'à
  0,8 mm trop haut, et le titre du bandeau affleurait le bord (D-010).
- **Crénage coupé et retrait des gabarits Chromium neutralisé** (D-005) : sans eux, les lignes ne se coupent plus
  aux mêmes mots.
- **Encodage des filtres** : IFS refuse l'espace encodée « + » (400). `LecteurIFS` encode en `%20` ; ne pas passer
  de `params=` à `requests` directement.
- **Compte technique** : en `client_credentials`, le jeton se présente comme `service-account-<client>` ; l'utilisateur
  de service IFS doit avoir ce web user, sinon `ORA-20105 Login.FUSRNULL`. `TALEND_SERVICE` ne convient pas,
  `ARMONY_SVC` oui (droits d'Armony, toutes les sociétés).
- **Droits différents d'Armony** : une projection que le rôle d'Armony n'a pas répond 403 (ex. contact de livraison
  du projet par `ProjectDefinitionHandling`) ; lire la même source qu'Armony (souvent une API d'entité).
- **Mentions et pied de page par société** : seule GAE est renseignée dans `ressources/textes/` ; une pièce d'une
  autre société sort sans mentions légales. Source OData encore à trouver (spec du bon, Q5).
- **Polices** : sur Linux, Carlito et Liberation Sans remplacent Calibri et Arial (mêmes métriques) ; mesurer aussi
  le PDF produit dans le conteneur.
- **Documents à valeur fiscale** (facture, situation) : leur PDF part aussi vers Esker (interface Talend INT-281) ;
  la recette associe la comptabilité.
