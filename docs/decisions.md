# Décisions

Une décision n'est jamais réécrite : elle est complétée ou remplacée par une suivante, avec renvoi.

## D-001 — L'application produit le PDF elle-même (26/10/2026)

Armony (Ootary) n'intervient ni pour les données ni pour le rendu. Le projet Armony et un PDF qu'il a produit servent
de **cahier des charges** : quels champs, quelles règles, quelle mise en page. L'export Armony se lit dans le dépôt
`armony-projects`.

## D-002 — Les données viennent des projections OData, à partir du numéro (26/10/2026)

Armony part des données du rapport IFS, donc d'une impression IFS. Une impression IFS **écrit** : elle marque la
commande communiquée et ajoute une ligne d'historique (constaté par tests-automatisés-IFS le 25/10/2026). Un bouton
qui produit un document ne doit pas avoir cet effet : l'application lit les projections, en lecture seule, à partir
du seul numéro.

Conséquence : ce que le rapport IFS calcule (mentions, pied de page, filtrage des textes document) doit être
retrouvé dans les projections. Ce qui ne l'est pas encore est listé dans la spec (§ 7 et § 8).

## D-003 — L'utilisateur lit la commande, un compte technique lit la référence (26/10/2026)

La commande est lue avec le jeton de l'utilisateur (SSO sur le realm IFS) : ses droits et ses sites s'appliquent
sans rien réimplémenter. Mais un acheteur n'ouvre pas `CompanyHandling`, `PersonHandling`, `PhrasesHandling`,
`PdfInsertsHandling` ni `ReportImagesHandling` (catalogue de droits de CFG), qu'Armony lit avec son propre compte
(`GAIFS_RF_ARMONY`). Ces lectures passent donc par un compte technique **facultatif** ; sans lui, par l'utilisateur,
et ce qui manque est signalé sans bloquer le document.

Un compte de service IFS sans utilisateur de service rattaché ne lit rien (`ORA-20105 Login.FUSRNULL`, constaté par
ga-commande) : le client Keycloak de l'application doit en avoir un.

## D-004 — HTML + Chromium pour le rendu (26/10/2026)

Le gabarit est du HTML/CSS (Jinja2) : lisible et modifiable sans outil dédié. Chromium (Playwright 1.58, la version
de tests-automatisés-IFS) sait répéter l'en-tête de tableau et numéroter « n/N » dans son pied de page. Les CGA sont
ajoutées ensuite (pypdf), hors numérotation, comme dans Armony.

## D-005 — La mise en page est calée sur Armony au dixième de millimètre (26/10/2026)

Positions, polices et coupures de ligne sont mesurées sur le PDF Armony de C106553 et réglées jusqu'à un écart
inférieur à 0,3 mm. Deux réglages ne se devinent pas et sont commentés dans `style.css` : le **crénage désactivé**
(DynamicPDF n'en fait pas ; avec, le texte est 0,5 % plus étroit et les lignes ne se coupent plus aux mêmes mots) et
le **retrait de 0,4 cm** que Chromium ajoute à ses gabarits d'en-tête et de pied.

Quand le script Armony et ce qu'il imprime divergent (condition toujours vraie, branche désactivée), c'est **ce qui
s'imprime** qui est reproduit, et l'écart est noté dans la spec.

## D-006 — Vitesse : lectures parallèles, Chromium gardé ouvert (26/10/2026)

Premier essai réel sur CFG : le PDF sort, mais « beaucoup trop long ». Trois causes côté application : une vingtaine
de lectures IFS en série, une lecture de textes document **par ligne**, et un Chromium lancé à chaque PDF (3,7 s,
pour 0,7 s de rendu). Désormais : tout ce qui ne dépend que de l'en-tête part en même temps (8 lectures
simultanées au plus), les textes document se lisent en une requête, et un seul Chromium vit dans un fil dédié,
lancé avec le serveur.

## D-007 — Le temps de chaque génération est consigné (26/10/2026)

Demande de Benoit : garder le temps de génération de chaque bon de commande. Une ligne JSON par demande dans
`data/generations.jsonl` (hors dépôt : elle nomme utilisateurs et commandes), consultable sur `/generations`, avec
le détail lecture IFS / rendu PDF et l'appel IFS le plus lent : c'est ce qui dira où passe le temps quand ce n'est
plus l'application.

## D-008 — La cible : prendre la place d'Armony dans l'impression IFS (29/10/2026)

Constat de Benoit : aujourd'hui, l'utilisateur prévisualise le bon depuis la boîte d'impression d'IFS et l'envoie au
fournisseur par e-mail depuis la même boîte. Un bouton qui ouvre l'application à côté ne remplace pas ce geste :
l'aperçu, l'e-mail et l'archive resteraient à Armony, qu'on ne pourrait donc pas arrêter.

Décision (Benoit) : l'application se branche **là où Armony se branche**, sur les événements IFS qui interceptent
l'aperçu et l'impression de la disposition « Armony layout ». Ce circuit a été relevé sur CFG (spec § 5). Pour
l'utilisateur, rien ne change.

Conséquences :

- **Complète D-002.** Le bouton d'aperçu reste possible, en option, en lecture seule. Le circuit d'impression, lui,
  écrit, mais uniquement ce qu'Armony écrit : le PDF de l'archive, son travail d'impression, l'état « imprimé ». La
  commande est marquée communiquée par IFS à l'ouverture de la boîte, comme aujourd'hui, avant toute éditique.
- **Complète D-003.** Dans le circuit d'impression, c'est IFS qui appelle l'application, sans navigateur ni jeton
  d'utilisateur. Le contrôle d'accès est celui d'IFS : on n'imprime que les commandes qu'on ouvre. L'application lit
  tout avec le compte technique, qui a besoin de droits d'écriture limités, sur le modèle de `GAIFS_RF_ARMONY`.
- L'application envoie l'e-mail elle-même, comme Armony, avec les pièces GED (spec § 5.3). Il lui faut un serveur
  SMTP.
- L'aiguillage se fait par disposition : le bon de commande passe à l'application, les quatre autres éditiques
  restent à Armony jusqu'à leur reprise.

Pas encore construit. Ce qui reste à trouver est dans la spec (Q11 à Q14).

## D-009 — Brancher par `ARMONY_SERVER`, avec l'identité d'Armony, hébergé sur Render (29/10/2026)

Relevé sur CFG (spec § 5.2) : les trois appels d'IFS vers Armony partent de l'URL du paramètre système
`ARMONY_SERVER`. Décisions de Benoit, DSI :

- **Aiguillage** : l'application répond aux adresses d'Armony (`/GetDownload.aspx`, `/Execute.aspx`) et l'on pointe
  `ARMONY_SERVER` vers elle. Le paramètre vaut pour toutes les éditiques : ce qui n'est pas le bon de commande est
  relayé tel quel à Armony (`ARMONY_RELAIS`). Retour arrière : la valeur d'origine, gardée par
  `outils/armony_server.py`. Le basculement se fait par l'API.
- **Identité** : le client d'Armony, `ARMONY_SVC` (utilisateur de service `ARMONY_SERVICE`, rôle `GAIFS_RU_ARMONY`).
  `TALEND_SERVICE` a été écarté : en `client_credentials`, son jeton (`service-account-talend_service`) ne correspond
  pas au web user de l'utilisateur IFS `TALEND_SERVICE`, et IFS répond `ORA-20105`.
- **Hébergement** : Render, région Francfort, instance payante (l'offre gratuite se met en veille et l'aperçu
  synchrone expirerait). Pas de filtrage par adresse IP possible.
- **Authentification** : aucune pour l'instant, comme vers Armony. Un segment secret dans l'URL viendra dans un
  second temps.
