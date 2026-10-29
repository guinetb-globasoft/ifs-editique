# Éditiques IFS — sans Armony

Application FastAPI qui produit les éditiques d'IFS Cloud (PDF) à la place d'Armony (Ootary) : l'application lit
IFS, met en page en HTML, Chromium rend le PDF. **Cible (D-008)** : prendre la place d'Armony dans l'impression IFS
(aperçu, OK, e-mail depuis la boîte d'impression), pas encore construit. **Fait** : un bouton d'aperçu qui ouvre
`/commande-achat/<n°>`.

- Logiciel : [README.md](README.md). Spec du bon de commande : [docs/specs/commande-achat.md](docs/specs/commande-achat.md).
  Décisions : [docs/decisions.md](docs/decisions.md).
- Cahier des charges de chaque éditique : le projet Armony dans `..\armony-projects` (une branche par environnement ;
  `PROD-PROD` fait foi). Armony n'est **jamais** une dépendance de l'application.
- Dépôt : https://github.com/GA-SA/editique-ifs (branche `main`), déployé sur Render par `render.yaml`.

## Commandes

```powershell
.\demarrer.ps1 -Rechargement                       # venv, dépendances, Chromium, serveur
.\.venv\Scripts\python.exe -m pytest tests -q      # hors ligne
.\.venv\Scripts\python.exe outils\apercu.py        # PDF sans IFS -> sorties\
```

## État au 29/10/2026 — version 0.3.0

- 🎯 Cible revue le 29/10 (D-008) : se brancher sur l'impression IFS à la place d'Armony. Circuit Armony relevé en
  réel sur CFG : spec § 5.
- 0.3.0 (D-009) : `app/impression.py` répond aux adresses d'Armony (aperçu synchrone, OK en tâche de fond, relais
  du reste à Armony) ; `Dockerfile` et `render.yaml` pour Render ; `outils/armony_server.py` bascule et rétablit
  `ARMONY_SERVER` (valeur d'origine CFG : `https://armony-qua.ga.fr/AxData_Rec`, gardée dans `sorties/`).
  **Testé hors ligne seulement** ; pas encore déployé ni basculé. E-mail non envoyé (pas de SMTP, Q13).
- 🐛 0.2.1 : jusqu'en 0.2.0, **toutes les lectures filtrées échouaient en réel** (IFS refuse l'espace encodée « + »,
  400) ; le premier PDF réel de CFG avait donc des champs vides. Corrigé et vérifié en réel sur CFG le 29/10 :
  C105125, 25 appels sans échec, aucun avertissement, lecture 5,1 s, rendu 1,6 s.
- Essai d'écriture dans l'archive, sur CFG, avec retour arrière : `outils/essai_archive.py`.

- ✅ Bon de commande : mise en page mesurée contre le PDF Armony de C106553, écarts < 0,3 mm ; CGA jointes ; 53 tests
  hors ligne verts.
- ✅ Premier PDF réel sorti sur CFG (Benoit, client `TALEND_SERVICE` mis par lui dans `.env`) — mais trop lent.
  0.2.0 parallélise les lectures et garde Chromium ouvert ; **gain réel pas encore mesuré** : lire `/generations`.
- Chaque génération est consignée avec ses temps dans `data/generations.jsonl` (`/generations`), à la demande de Benoit.
- ⚠️ Le contenu réel n'a pas encore été comparé au PDF Armony de la même commande : `/commande-achat/<n°>/donnees`,
  puis les questions Q1–Q10 de la spec.
- Présentation de la solution (deck, 29/10) : https://claude.ai/artifact/58ANspGFg3tSrni34gqW7w
- ⚠️ Mentions et pied de page lus dans `ressources/textes/<société>.json` (seul GAE) en attendant leur source OData.

## Invariants

- **Le bouton est en lecture seule.** `app/ifs/lecture.py` n'a que des GET (D-002). Le circuit d'impression
  (D-008) n'écrit que ce qu'Armony écrit, et seulement par `app/ifs/ecriture.py` (PDF de l'archive, suppression du
  travail reçu, événements `ARMONY_REPORT_JOB` / `ARMONY_REPORT_PRINT`) ; aucune autre écriture.
- **Ne jamais deviner un nom IFS.** Le vérifier dans le catalogue (`..\mcp-ifs\data\catalogue-cfg.sqlite`, tables
  `champs`, `entites`, `navigations`, `droits`) ou dans une requête Armony, et dire dans la spec lequel des deux.
- **Énumérations filtrées après lecture**, jamais dans `$filter`.
- **Bouton : la commande avec le jeton de l'utilisateur, la référence avec le compte technique s'il existe** (D-003).
  Circuit d'impression : tout avec le compte technique, IFS ayant contrôlé l'accès (D-008). Une source de référence
  illisible n'arrête pas le document : avertissement, champ vide.
- **Reproduire ce qu'Armony imprime**, pas ce que son script semble vouloir ; noter l'écart dans la spec.
- **Mise en page** : toute retouche se vérifie contre la référence (positions mesurées, pas à l'œil). Ne pas
  réactiver le crénage ni retirer la neutralisation du retrait des gabarits Chromium (D-005).
- Le jeu `exemples/` est **reconstitué** (coordinateur fictif) : pas de donnée personnelle réelle dans le dépôt.
  Les PDF produits vont dans `sorties/`, hors dépôt.

## Conventions

- Code, docs et messages en français ; noms IFS tels qu'IFS les écrit.
- Une version par commit (`app/version.py`).
- Ne pas annoncer qu'une chose fonctionne sans l'avoir exécutée, et dire si c'était hors ligne ou en réel.
