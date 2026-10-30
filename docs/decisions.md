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

→ D-011 : le bouton est retiré. La lecture des projections à partir du numéro reste celle du circuit d'impression.

## D-003 — L'utilisateur lit la commande, un compte technique lit la référence (26/10/2026)

La commande est lue avec le jeton de l'utilisateur (SSO sur le realm IFS) : ses droits et ses sites s'appliquent
sans rien réimplémenter. Mais un acheteur n'ouvre pas `CompanyHandling`, `PersonHandling`, `PhrasesHandling`,
`PdfInsertsHandling` ni `ReportImagesHandling` (catalogue de droits de CFG), qu'Armony lit avec son propre compte
(`GAIFS_RF_ARMONY`). Ces lectures passent donc par un compte technique **facultatif** ; sans lui, par l'utilisateur,
et ce qui manque est signalé sans bloquer le document.

Un compte de service IFS sans utilisateur de service rattaché ne lit rien (`ORA-20105 Login.FUSRNULL`, constaté par
ga-commande) : le client Keycloak de l'application doit en avoir un.

→ D-011 : avec le bouton, la lecture par l'utilisateur disparaît ; tout est lu par le compte technique.

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

→ D-009 pour le branchement ; D-011 : bouton retiré, SMTP d'Armony non repris, pas d'impression papier.

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

→ D-011 : client Keycloak propre par realm ; le renvoi à Armony ne va pas en PROD.

## D-010 — La mise en page se mesure à la ligne de base (30/10/2026)

Complète D-005. Le calage de D-005 comparait le haut des boîtes de texte. DynamicPDF (Armony) et Chromium ne
déclarent pas la même hauteur de police : sur cette mesure, tout tombait sous 0,3 mm, alors qu'à la ligne de base,
là où les caractères sont réellement posés, nos textes étaient jusqu'à 0,8 mm trop haut. Le défaut est apparu quand
Benoit a vu le haut du titre du bandeau « haché » (blanc sur blanc, au bord du rose).

Désormais : toute mesure de fidélité se fait à la ligne de base, avec `outils/mesurer_mise_en_page.py` (et l'agent
`verif-mise-en-page`). État au 30/10 sur C106553 : 53 textes communs, tous sous 1 mm, 15 sous 0,3 mm ; bandeau et
titre à 0,05 mm (0.3.3). Le recalage du reste se fait par famille de textes (classe CSS), pas texte par texte.

## D-011 — Réponses de la DSI pour la cible (30/10/2026)

Réponses de Benoit, DSI, au questionnaire de la cible (document « réponses aux questions » :
https://claude.ai/artifact/Y3BD7oXCfZEVYyKtAW7Yud) :

- **Bouton d'aperçu retiré** : on supprime ce qui ne sert pas, et l'aperçu passe par la boîte d'impression d'IFS. Le
  bouton (`/commande-achat/<n°>`), la connexion des utilisateurs au realm (`app/ifs/sso.py`) et le secret de session
  sortent de l'application ; il ne reste qu'une identité, le compte technique. **Remplace** le bouton de D-002 et de
  D-008 et la lecture par l'utilisateur de D-003. Pas encore fait dans le code. Les routes de support (`/donnees`,
  `/generations`) passent par la même connexion : leur sort reste à trancher.
- **Compte technique propre** : un client Keycloak dans chacun des cinq realms, avec utilisateur de service et les
  droits d'Armony, sur le modèle d'`ARMONY_SVC`. Complète D-009 : `ARMONY_SVC` en attendant. À créer par
  l'administrateur IFS.
- **Authentification de l'appel d'IFS** : le segment secret (D-009) est le mieux que permet la fonction standard
  d'IFS ; Armony n'en a aucune.
- **E-mail** : le serveur SMTP et l'expéditeur d'Armony, paramétrés par le N2 Infra, ne sont pas repris ; l'expéditeur
  est une adresse `@ga.fr` (spec Q13). Plusieurs destinataires sont possibles, en copie et en copie cachée, tous tirés
  d'IFS (spec Q15).
- **Pas d'impression papier** chez GA : au pire, l'utilisateur ouvre le PDF et l'imprime.
- **Volumes** : une centaine d'impressions par jour au plus, étalées sur la journée, ni la nuit ni le week-end. Une
  instance par environnement suffit.
- **Fiche RAC** : lancée automatiquement chaque semaine. Ce n'est pas un rapport IFS : un planificateur la déclenche.
- **Pas de cohabitation avec Armony** : le projet tient en 3 jours de développement et 2 de recette ; toutes les
  éditiques sont reprises avant de basculer la PROD. Le renvoi à Armony (D-009) ne sert qu'aux essais tant qu'elles ne
  le sont pas, et ne va pas en PROD.
