"""La version de l'application, en un seul endroit.

`MAJEUR.MINEUR.CORRECTIF`, une version par commit, comme les autres applications
IFS de GA : elle sert à **nommer ce qui tourne** (dans un PDF, un journal, une
capture d'écran), pas à promettre une compatibilité.

| Version | Date | Ce qui la caractérise |
|---|---|---|
| 0.1.0 | 26/10/2026 | Première éditique : la commande d'achat, à l'image d'Armony |
| 0.2.0 | 26/10/2026 | Lectures IFS en parallèle, Chromium gardé ouvert, temps de chaque génération consigné (`/generations`) |
| 0.2.1 | 29/10/2026 | Correctif : les lectures filtrées (`$filter`) échouaient toutes en réel, IFS refusant l'espace encodée « + » ; outil d'essai `outils/essai_archive.py` |
| 0.2.2 | 29/10/2026 | Le PDF est signé : titre « Bon de commande <n°> », application « ifs-app-editique <version> » dans ses propriétés |
| 0.3.0 | 29/10/2026 | Branchement sur l'impression IFS aux adresses d'Armony (`/GetDownload.aspx`, `/Execute.aspx`), relais à Armony du reste, écritures d'Armony (`app/ifs/ecriture.py`), image Docker pour Render |
| 0.3.1 | 29/10/2026 | Correctif : IFS passe les clés en décimal (`RESULT_KEY_=56608.0`) ; le premier aperçu réel répondait 500 |
| 0.3.2 | 29/10/2026 | Correctif : répondre au workflow d'IFS le XML d'Armony (`<Root><Error>Dummy</Error></Root>`) et non « OK » ; la boîte affichait « erreur serveur » |
| 0.3.3 | 29/10/2026 | Titre du bandeau et lignes « COMMANDE / REVISION » recalés sur Armony par la ligne de base : le haut du titre était coupé |
| 0.3.4 | 30/10/2026 | Documentation : réponses de la DSI (D-011), mesure à la ligne de base (D-010, `outils/mesurer_mise_en_page.py`), skills et agents du projet ; code inchangé |
"""

VERSION = "0.3.4"
