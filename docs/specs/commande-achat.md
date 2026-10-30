# Spécification — éditique « Bon de commande » (commande d'achat IFS)

| | |
|---|---|
| Version de la spec | 1.2, 30/10/2026 : réponses de la DSI (D-011) : bouton à retirer, pas d'impression papier, plusieurs destinataires |
| Application | ifs-app-editique 0.3.4 : branchée sur l'impression IFS de CFG ; le bouton (§ 2.2) existe encore, à retirer |
| Remplace | Armony (Ootary), projet **`Commande_dachat v1`** — disposition IFS « Armony layout » du rapport `PURCHASE_ORDER_PRINT_REP` (`PurchaseOrderPrintRepArmony.rdl`) |
| Référence visuelle | C106553 imprimé par Armony sur TST le 25/10/2026 (`tests-automatisés-IFS/outputs/editiques/MV-027_ADMIN_C106553_58470.pdf`) |
| Statut | Données lues en réel sur CFG (aperçus de C105125 et C103212) ; comparaison champ par champ avec Armony en recette. Mise en page : tous les textes à moins de 1 mm de la référence à la ligne de base, 15 sur 53 sous 0,3 mm (D-010). E-mail non envoyé : pas de SMTP (Q13). |

## 1. Objet

Produire le bon de commande d'achat d'IFS Cloud **sans Armony ni Ootary** : l'application lit la commande dans IFS,
la met en page et rend le PDF. Le document doit être identique à celui d'Armony, CGA jointes comprises.

L'application prend **la place d'Armony dans l'impression IFS** : aperçu, impression et envoi par e-mail depuis la
boîte d'impression, sans rien changer pour l'utilisateur (D-008). Le bouton d'aperçu direct construit en premier est
à retirer (D-011).

### Ce qui fait foi

Le projet Armony `Commande_dachat v1` est **le même en TST et en PROD** (dépôt `armony-projects`, branches `TST-MIGR` et
`PROD-PROD`, état au 16/10/2026 : seules les valeurs de test des paramètres diffèrent). C'est lui qui est spécifié ici.
Les autres versions ne sont pas reprises :

| Version | Où | Écart avec la v1 de PROD |
|---|---|---|
| `Commande_dachat v1` | CFG-REC | ~80 lignes : mêmes règles, blocs de script réorganisés |
| `Commande_dachat v1` | TRN-PREPROD, UAT-TEST | 400+ lignes : version antérieure (colonnes du rapport en `MAJUSCULES`) |
| `Commande_dachat_` | PROD-PROD | ancien projet, 500 lignes d'écart |

⚠️ Quelle version est **branchée** en PROD se lit dans IFS (`CustomProjectionArmonyLayoutConfig`, couple rapport +
disposition → fichier axdata, § 5.1). C'est la question ouverte Q1.

## 2. Déclenchement et identité

Deux points d'entrée, un seul document.

### 2.1 Par l'impression IFS : la cible, construite et essayée en réel sur CFG

L'utilisateur fait comme aujourd'hui : **Partager › Imprimer commande** sur la commande d'achat. La boîte « Format et
impression rapport » propose la disposition « Armony layout », la langue, l'imprimante, la case **Envoyer e-mail**
(cochée par défaut, paramètre système `SEND_EMAIL_CHECKBOX`) et une adresse, celle de l'utilisateur par défaut. Puis
**Prévisualisation** ou **OK** (boîte relevée par tests-automatisés-IFS sur TST le 25/10/2026).

IFS appelle alors l'application à la place d'Armony, par le circuit décrit au § 5.

| Règle | |
|---|---|
| **RG-35** | L'application est appelée **par IFS**, avec la clé d'archive (`RESULT_KEY`) et le n° de travail d'impression. C'est IFS qui contrôle ce que l'utilisateur peut imprimer. L'application lit tout avec le compte technique (D-008). |
| **RG-36** | **Prévisualisation** : le PDF de l'application remplace celui d'IFS dans l'archive avant que la boîte l'affiche. Rien n'est envoyé ni marqué imprimé. |
| **RG-37** | **OK** : le même PDF remplace celui de l'archive. Puis l'e-mail part si une adresse est saisie (§ 5.3), et l'archive passe « imprimée ». Pas d'impression papier : GA n'en fait pas (D-011). |
| **RG-38** | Seule la disposition `PurchaseOrderPrintRepArmony.rdl` du rapport `PURCHASE_ORDER_PRINT_REP` passe par l'application. Les autres dispositions restent à IFS, les autres éditiques à Armony. |

Ce n'est pas l'éditique qui marque la commande communiquée. IFS le fait dès l'ouverture de la boîte : il ajoute
« Commande imprimée » à l'historique et passe `Communicated` à vrai, comme aujourd'hui.

### 2.2 Par un bouton d'aperçu : construit, à retirer (D-011)

1. Dans IFS, sur l'écran **Commande d'achat**, un bouton (commande personnalisée de Page Designer) ouvre dans un nouvel
   onglet : `https://<hôte de l'application>/commande-achat/${OrderNo}`.
2. Sans session, l'application renvoie au realm IFS. L'utilisateur y est déjà connecté : il ne saisit rien.
3. Le PDF s'affiche dans l'onglet ; `?telecharger=1` le propose en téléchargement.

Un appelant non navigateur présente son jeton IFS (`Authorization: Bearer …`) : c'est l'API.

| Règle | |
|---|---|
| **RG-01** | La commande est lue **avec l'identité de l'utilisateur**. Une commande que l'utilisateur ne voit pas dans IFS (autre site, droits) répond « n'existe pas ou vous n'y avez pas accès » (404). |
| **RG-02** | Les données de référence (§ 4.2) sont lues avec le **compte technique** s'il est configuré, sinon avec l'utilisateur. |
| **RG-03** | Une donnée de référence illisible **n'empêche pas** le document : le champ reste vide et l'avertissement est listé dans `/commande-achat/<n°>/donnees`. La commande, ses lignes et ses frais, eux, sont indispensables : leur échec arrête tout. |
| **RG-04** | **Le bouton n'écrit rien dans IFS** : pas d'archive, pas d'e-mail, la commande n'est pas marquée « communiquée ». C'est un aperçu. |

## 3. Le document

A4 portrait, Calibri 11 sauf mention. Positions en mm depuis le coin haut gauche, mesurées sur la référence.

### 3.1 Répété à chaque page

| Élément | Contenu | Règle |
|---|---|---|
| Logo | logo de la société de la commande | Cadre 40 × 30 mm en (15, 0), image contenue. **RG-10** : société sans logo dans IFS → pas de logo. Logo illisible (droits) → logo de `ressources/logos/` et avertissement. |
| Pied de page | deux lignes, Arial 7, centrées sur 10–190 mm, à 281,7 et 284,7 | **RG-11** : les deux premières lignes du pied de page de la société. Provisoirement lues dans `ressources/textes/<société>.json` (Q5). |
| Numéro de page | « n/N », Arial 9, à (196, 284,6) | **RG-12** : N compte les pages du bon de commande, **pas celles des CGA**. |

### 3.2 En-tête de la page 1

| Élément | Contenu |
|---|---|
| Bandeau rose (#EC007E), 11 → 201,6 mm, 24,4 → 36 mm | « BON DE COMMANDE N° <n°> » puis « EN DATE DU <jj/mm/aaaa> », Calibri gras 14, blanc, centrés. **RG-13** : commande à l'état *Planifié* → « BROUILLON DE COMMANDE <n°> ». |
| Sous le bandeau, gris gras centré | « COMMANDE », puis « REVISION Nº <révision> ». |

Quatre cadres de 92 × 60 mm, filet noir : société en (10, 50), fournisseur en (106, 50), livraison en (10, 115),
modalités de facturation en (106, 115). Titres en rose gras centré.

**Cadre société (« client »)** — titre : nom de la société.

| Libellé | Valeur | Règle |
|---|---|---|
| SIRET : | numéro fiscal de type `SIRET` de l'adresse document de la société | |
| Adresse de facturation : | adresse document de la société, Arial 10 : adresse 1, adresse 2, « CP Ville » | **RG-14** : adresses 3 à 6 et pays non imprimés (Armony). |
| Projet ou section : | nom du projet de la commande | **RG-15** : vide sans projet. Armony prévoyait la section (CodeD de la 1re ligne) pour une commande sans projet, mais sa condition rend « projet » toujours vrai : la section n'est **jamais** imprimée. On reproduit ce qui s'imprime. |
| Numéro projet : | identifiant du projet | |
| Contact : / Mail : / Téléphone : | coordinateur de la commande (*Authorizer*) : nom, e-mail, téléphone | **RG-16** : moyen de communication par défaut d'abord ; téléphone fixe, sinon mobile. |

**Cadre fournisseur** — titre : nom du fournisseur. Valeurs en Arial 10.

| Libellé | Valeur | Règle |
|---|---|---|
| SIRET : | identifiant de l'adresse document du fournisseur | **RG-17** : chez GA, cet identifiant **est** le SIRET. |
| Adresse : | adresse document du fournisseur | **RG-18** : deux premières lignes seulement (Armony : `DataRowNumber < 3`). |
| Contact : | contact fournisseur de la commande | |
| Mail : | e-mail du fournisseur sur son adresse document | |
| Conditions de paiement : | libellé des conditions de paiement de la commande | |
| Mode de règlement : | mode de paiement **par défaut** du fournisseur pour la société (Calibri 11) | |

**Cadre livraison**

| Libellé | Valeur | Règle |
|---|---|---|
| Date de livraison : | date souhaitée de la **première ligne** | |
| Contact : | « <nom>, <e-mail> » du moyen e-mail de l'adresse projet de la commande, puis la référence de la commande | **RG-19** : Armony ajoute aussi `PO_HEADERS.NAME` (Q4). La branche Armony « sans projet » (contact = coordinateur) ne s'exécute jamais (voir RG-15). |
| Adresse : | lignes 1 à 6 de l'adresse de livraison de la commande | CP et ville non imprimés (Armony). |
| *(sans libellé)* | textes document de la commande, séparés par « , » | Variable Armony `Horaire_de_livraison`. Q6 sur les types de sortie. |
| Commentaire client : | note de la commande (*LabelNote*), gras italique souligné | |

**Cadre modalités de facturation** (Arial 10)

| Bloc | Valeur |
|---|---|
| Hors e-facture, à 124 mm | phrase IFS **ACH05** + e-mail de la société sur son adresse document |
| E-facture, à 144,3 mm | phrase IFS **ACH04** + moyen *Messenger* de la société sur son adresse document (identifiant de routage de la plateforme agréée) |

### 3.3 Le tableau (à partir de 180,8 mm sur la page 1, de 25 mm sur les suivantes)

191 mm de large, en-tête rose répété à chaque page.

| Colonne | Largeur | Valeur | Format |
|---|---|---|---|
| REF CLIENT | 15 | référence article (vide pour une ligne sans article) | centré |
| REF FOUR | 15 | référence fournisseur | centré |
| DESIGNATION | 65 | description de la ligne | |
| UNITE | 15 | unité d'achat | centré |
| QUANTITE | 19 | quantité d'achat restant due (*BuyQtyDue*) | `2 000,00` |
| PRIX UNITAIRE | 18 | prix unitaire d'achat en devise (*FbuyUnitPrice*) | `2 000,00` |
| REMISE % | 14 | remise | **RG-20** : `0,00` si aucune |
| MONTANT HT | 19 | montant net **en devise société** (*NetAmountBase*) | |
| TVA % | 11 | taux du code taxe de la ligne | |

| Règle | |
|---|---|
| **RG-21** | Lignes **article et sans article réunies**, triées par n° de ligne puis de livraison (numériquement). |
| **RG-22** | Les lignes **annulées** ne sont pas imprimées (Armony part des lignes du rapport IFS). À confirmer (Q3). |
| **RG-23** | Sous une ligne livrée à une **adresse du projet** : ligne de détail « Contact, adresse et horaire de livraison :  <nom>,  <adresse> <contact> » (filets verticaux seulement). L'adresse s'écrit « rue, CP - Ville, Département, FR - FRANCE ». GA range l'horaire dans le champ *Contact* de l'adresse projet. Les doubles espaces sont ceux d'Armony. |
| **RG-24** | Puis, si la ligne a des textes document : une ligne de détail avec ces textes, séparés par « , ». |
| **RG-25** | Les **frais** suivent les lignes : désignation, quantité, prix, montant net (devise de la commande), TVA ; colonnes de référence, unité et remise vides. |
| **RG-26** | Dernière ligne : « MONTANT TOTAL HT EN EUROS » (gris gras, à droite) et le total HT IFS au format `2 000,00 €`. Si ce total diffère de la somme des montants imprimés, le document part et l'écart est signalé (Q2). |
| **RG-27** | La variante « HORAIRE DE LIVRAISON » du script Armony (designation enrichie quand un texte document contient ce mot) est **désactivée** dans Armony : non reprise. |

### 3.4 Après le tableau

| Élément | Règle |
|---|---|
| Mentions | **RG-28** : une mention par paragraphe (6 mm au moins), séparées de 4,9 mm, 4,5 mm sous le tableau. Provisoirement lues dans `ressources/textes/<société>.json` (Q5). Pour GAE : prix fermes, CGA simplifiées, mentions obligatoires de facture. |
| Signatures | « Nom et signature du fournisseur » à gauche, « Nom et signature du client » à 134 mm, jamais coupées. Elles passent en haut de la page suivante si la page est pleine (cas de C106553). |

### 3.5 Annexes : les CGA

| Règle | |
|---|---|
| **RG-29** | Après le bon de commande, la ou les CGA, dans cet ordre : **achat** si la case *Achats* est cochée **ou si aucune case ne l'est** ; **location** si *Location* est cochée ; **prestation** si *Prestation* est cochée (champs CUSTOM `Cf_Ga_Cdeha_Achats / _Location / _Prestation`). |
| **RG-30** | Les CGA sont les encarts PDF d'IFS (*Encarts PDF des rapports*) dont le nom contient « cga achat », « cga location », « cga prestation » ou « cga préstation » (sans distinction de casse). Si plusieurs correspondent : **la plus récente**. Armony prenait la dernière lue, ordre non garanti. |
| **RG-31** | CGA introuvable : le bon part sans elle et l'avertissement est listé. |

### 3.6 Formats et langue

| Règle | |
|---|---|
| **RG-32** | Nombres `### ### ##0,00` à la française, espace insécable en séparateur de milliers ; total suivi de « € ». |
| **RG-33** | Dates `jj/mm/aaaa`, partie date seule, sans conversion de fuseau. |
| **RG-34** | Libellés issus du fichier de traduction d'Armony (`gabarit/libelles.json`, colonne de `EDITIQUE_LANGUE`, défaut `fr`). Seule la colonne `fr` est remplie aujourd'hui ; un libellé sans traduction s'imprime en français. |

## 4. Sources IFS

« Vérifié » : **catalogue** = nom présent dans la métadonnée de CFG (moisson mcp-ifs du 17/09/2026) ; **Armony** = même
lecture faite par Armony en production ; **réel** = lu par cette application dans un IFS (aucun à ce jour).

### 4.1 Lu avec l'identité de l'utilisateur (`PurchaseOrderHandling`, la projection de l'écran)

| Donnée | Chemin | Vérifié |
|---|---|---|
| En-tête | `PurchaseOrderSet(OrderNo='…')` : OrderNo, Objstate, OrderDate, Revision, Company, DocumentAddressId, VendorNo, VendorName, DocAddrNo, ContactName, AuthorizeCode, AuthorizerName, ProjectId, ProjectName, ProjectAddressId, Address1–6, LabelNote, Reference, NoteId, Cf_Ga_Cdeha_* | catalogue |
| Lignes | `…/LinePartArray`, `…/LineNopartArray` (montant : `NetAmountBase` / `NetAmtBase`) | catalogue ; navigations de l'écran |
| Frais | `…/PurchaseOrderChargeArray` : Description, ChargedQty, ChargeAmount, TotalCurrency, FeeCode | catalogue |
| Nom de la société | `…/CompanyFinanceRef` : Description | catalogue (Q7 : Description = raison sociale ?) |
| Conditions de paiement | `…/PayTermIdRef` : Description | catalogue |
| Total HT | `…/OrderAmountRef` : OrderTotalCurr | catalogue (Q2) |
| Taux de TVA | `Reference_TaxCodeCommon` (Company) : FeeCode, FeeRate | catalogue |
| Adresse de facturation | `Reference_CompanyAddress` (Company, AddressId) | catalogue ; Armony (projection d'entité) |
| Adresse fournisseur | `Reference_SupplierInfoAddress` (SupplierId, AddressId) | catalogue |
| Adresses du projet | `Reference_ProjectAddressLov` (ProjectId) | catalogue |
| Noms de pays | `Reference_IsoCountry` (CountryCode) : Description | catalogue |

### 4.2 Données de référence (compte technique, sinon utilisateur)

Un acheteur (`GAIFS_RF_SVA_ACHAT`) **n'a pas accès** à la plupart de ces projections ; le rôle `GAIFS_RF_ARMONY` les a
toutes (catalogue de droits de CFG). D'où le compte technique (Q8).

| Donnée | Chemin | SVA_ACHAT | Vérifié |
|---|---|---|---|
| SIRET société | `CompanyHandling.svc/Reference_CompanyAddressTaxNumber` | – | catalogue |
| E-mail et routage de facturation | `CompanyHandling.svc/Reference_CommMethod` | – | catalogue |
| Logo | `CompanyHandling.svc/CompanySet(Company).Logotype` puis `ReportImagesHandling.svc/ReportLogoSet(ImageName)/FileData` | – | catalogue ; Armony |
| Coordonnées du coordinateur | `PersonHandling.svc/Reference_CommMethod` (Identity = AuthorizeCode) | – | catalogue (Q9) |
| Phrases ACH04 / ACH05 | `PhrasesHandling.svc/Reference_MpccomPhraseText` | – | Armony |
| E-mail fournisseur | `SupplierHandling.svc/Reference_CommMethod` | Custom | catalogue |
| Mode de règlement | `SupplierHandling.svc/Reference_PaymentWayPerIdentity` puis `Reference_PaymentWay` | Custom | catalogue |
| Contact de livraison du projet | `ProjectDefinitionHandling.svc/Reference_ProjectCommMethod` | Custom | catalogue |
| Textes document | `DocumentTextHandling.svc/Reference_DocumentText` (NoteId) | Full | catalogue |
| CGA | `PdfInsertsHandling.svc/ReportPdfInserts` puis `ReportPdfInserts(Id)/FileData` | – | catalogue ; Armony |

Les énumérations (`MethodId`, `PartyType`) sont filtrées **après lecture**, jamais dans `$filter` : leur nom de type
n'est pas prévisible et `ne` sur une énumération rend une liste vide sans erreur (constat de tests-automatisés-IFS).

## 5. Le circuit d'impression IFS, tel qu'Armony s'y branche

Relevé **en réel sur CFG le 29/10/2026**, en lecture seule (`EventActionHandling`, `FndSettings`,
`CustomProjectionArmonyLayoutConfig`, `ReportDefinitionsHandling`, `RoutingRulesHandling`), et dans le connecteur
Armony `scripts/ReportOk.axdata` (armony-projects, branche PROD-PROD). C'est ce circuit que l'application doit
reprendre (D-008).

### 5.1 L'aiguillage

| Élément | Sur CFG |
|---|---|
| Dispositions du rapport `PURCHASE_ORDER_PRINT_REP` | `PurchaseOrderPrintRep.rdl` (Portrait), `PurchaseOrderPrintRepArmony.rdl` (Armony layout), `PurchaseOrderPrintRep_us.rdl` : toutes de type Report Designer |
| Table d'aiguillage `CustomProjectionArmonyLayoutConfig` | 5 couples rapport + disposition gérés par Armony, chacun avec son fichier Armony. Bon de commande → `ReportWeb/9ecc9f74-….axdata` |
| Paramètre système `ARMONY_SERVER` | URL du service Armony : `https://armony-qua.ga.fr/AxData_Rec` |
| `CustomProjectionArmonyPhysicalPrinter` | vide : aucune imprimante physique Armony |

### 5.2 Les événements

Six événements personnalisés, des paquets d'application « PKG_DEV_Armony Report » et « PKG_DEV_Armony Layout » :

| Événement | Déclencheur | Action | Rôle |
|---|---|---|---|
| `ARMONY_REPORT_PRVW` | nouvelle ligne `PrintJobContents` pendant `PRINT_DIALOG_SVC.Do_Report_Direct_Print_Request`, disposition gérée par Armony | workflow `ARMONY_REPORT_PRVW` (*process augment*, après) | **Prévisualisation** : Armony produit le PDF pendant que la boîte attend |
| `ARMONY_REPORT_OK` | nouvelle ligne `ReportAddressLabel` | SQL : si la disposition est dans la table d'aiguillage, suspend puis annule le message de rapport d'IFS ; hors aperçu, lève `ARMONY_REPORT` | **OK** |
| `ARMONY_REPORT` | levé par `ARMONY_REPORT_OK` avec RESULT_KEY, PRINT_JOB_ID, USER_ID, langue, locale, disposition, copies | message d'application | transmet la demande à Armony |
| `ARMONY_REPORT_AGENT` | changement d'imprimante d'un travail par `PRINT_DIALOG_SVC.Do_Update_Printer_Id`, agent Aurena, sans e-mail | message d'application | impression locale par l'agent Aurena |
| `ARMONY_REPORT_JOB` | appelé par Armony (`ReportPrintersHandling.svc/Cf_EventAction`) | SQL : crée un travail `NO_PRINTOUT` avec `SEND_PDF=FALSE`, l'exécute, attend 30 s au plus, y écrit un GUID | donne à Armony un travail à lui, sans e-mail d'IFS |
| `ARMONY_REPORT_PRINT` | appelé par Armony en fin de traitement | SQL : `Archive_Distribution_API.Set_Printed`, imprimante et message « Requested By <utilisateur> » sur le travail | passe l'archive « imprimée » |

**Les trois appels vers Armony** (lus sur CFG le 29/10/2026) partent tous de l'URL du paramètre `ARMONY_SERVER`.
Aucune authentification n'est déclarée sur ces appels :

| Appel | Par | Requête | Mode |
|---|---|---|---|
| Aperçu | workflow `ARMONY_REPORT_PRVW` : lit l'utilisateur (`UserSettings`), puis `ARMONY_SERVER` (`FndSettings`), puis tâche HTTP | `GET {ARMONY_SERVER}/GetDownload.aspx?layout_name=ReportPreview.axdata&RESULT_KEY_=…&PRINT_JOB_ID_=…&USER_ID_=…` | **synchrone** : la boîte attend la réponse |
| OK | action `ARMONY_REPORT`, message d'application, connecteur `Http` | `{ARMONY_SERVER}/Execute.aspx?layout_name=ReportOk.axdata&AxAsync=True&RESULT_KEY_=…&PRINT_JOB_ID_=…&USER_ID_=…&LANGUAGE_CODE_=…&LAYOUT_NAME_=…&LOCALE_LANGUAGE_=…&LOCALE_COUNTRY_=…&COPIES_=…` | asynchrone |
| Agent Aurena | action `ARMONY_REPORT_AGENT`, même connecteur | `{ARMONY_SERVER}/Execute.aspx?layout_name=ReportAurenaAgent.axdata&PRINT_JOB_ID_=…` | asynchrone |

Le diagramme du workflow se lit par `WorkFlowBpmnHandling.svc/BpmnVersionSet(ProcessKey=…,Version=…)/BpaDiagram`,
qui est un flux. Dans `BpmnWorkflowDataSet`, le même champ est déclaré en texte et IFS y renvoie
`oracle.sql.BLOB@…` au lieu du contenu. L'adresse du message n'est pas une règle IFS Connect : elle est portée par
l'action d'événement elle-même (`AddressData`).

**Le script d'aperçu d'Armony** (`ReportPreview.axdata`, fourni par Benoit le 29/10/2026) :
1. il lit une fois la ligne `PdfArchiveSet` du travail (`ResultKey`, `PrintJobId`), et s'arrête en erreur si elle
   n'existe pas encore ;
2. il choisit son projet par la table d'aiguillage, produit le PDF et le dépose par `PATCH …/Pdf` (`If-Match`) ;
3. pour l'agent Aurena seulement, il écrit l'e-mail de l'utilisateur dans les réglages du travail ;
4. il **répond un fichier XML** `response_armony.xml` : `<Root><Error>Dummy</Error></Root>`. Le workflow d'IFS lit
   cette réponse. Un simple « OK » en texte le fait échouer, et la boîte affiche « PrintDialog/PrintDialog (erreur
   serveur) » alors que le PDF est déjà dans l'archive (constaté sur CFG, corrigé en 0.3.2).

Le workflow d'aperçu se déclenche sur toute demande d'impression de la boîte, OK compris : sur OK, IFS appelle
donc l'aperçu, puis `Execute.aspx`.

**Conséquence** : `ARMONY_SERVER` est l'aiguillage unique. Si on le pointe vers l'application, et qu'elle répond aux
mêmes adresses, IFS l'appelle à la place d'Armony sans autre changement. Le retour arrière consiste à remettre la
valeur d'origine. En revanche, ce paramètre vaut pour les cinq éditiques : ce qui n'est pas le bon de commande doit
être relayé à Armony, tant que les autres éditiques ne sont pas reprises. Ce renvoi ne va pas en PROD (D-011).

### 5.3 Ce que fait Armony quand il est appelé

D'après le connecteur `ReportOk.axdata` et le projet `Commande_dachat v1` :

1. Il lit le travail d'impression (`ReportArchive.svc/PrintJobSet`), le supprime, puis s'en crée un par
   `ARMONY_REPORT_JOB`.
2. Il lit l'archive (`ReportArchive.svc/ArchiveSet`, par `ResultKey`) pour le rapport et ses paramètres, et les
   réglages du travail (`Settings`), dont `SEND_PDF_TO`, l'adresse saisie dans la boîte.
3. Il choisit son projet par la table d'aiguillage et l'exécute.
4. Il **remplace le PDF de l'archive** : `PrintDialog.svc/PdfArchiveSet(ResultKey=…,Id='…')/Pdf` (PATCH, `If-Match`).
   C'est ce PDF que la boîte affiche. `PdfSize` garde la taille du rendu d'IFS (constat INT-281, ga-talend).
5. Il imprime sur l'imprimante physique déclarée pour l'imprimante IFS, s'il y en a une.
6. Il **envoie l'e-mail lui-même**, par son serveur SMTP, si une adresse est saisie :

   | Champ | Valeur |
   |---|---|
   | À | l'adresse de la boîte (`SEND_PDF_TO`), sinon `PDF_EVENT_PARAM_1` du travail |
   | Copie | l'utilisateur (son moyen de communication par défaut, sinon l'e-mail de son compte), le coordinateur, l'acheteur |
   | Objet | « Commande N°<n°> – site <site> – Libellé societé site <société> » |
   | Corps | « Bonjour, Vous trouverez ci-joint notre bon de commande n° <n°>. Ce numéro doit être indiqué sur votre facture. Nous vous remercions de bien vouloir en accuser réception par retour de mail. Cordialement, <nom de l'acheteur> » |
   | Pièces jointes | le PDF ; les documents GED des classes `PJ_COMMANDE` et `CRM PANEL` de la commande et `PJ_CDE-PRJ` du projet, non concaténés au PDF |

   L'adresse proposée par défaut est celle de l'utilisateur : pour envoyer au fournisseur, il la remplace.
   Plusieurs destinataires sont possibles, en copie et en copie cachée, tous tirés d'IFS (DSI, 30/10/2026) : comment
   IFS les porte dans le travail d'impression est la question Q15.
7. Il lève `ARMONY_REPORT_PRINT`, qui passe l'archive « imprimée ».

### 5.4 Ce que l'application devra faire

Reprendre ce contrat pour la seule disposition du bon de commande (RG-35 à RG-38) :
- être appelée par IFS à la place d'Armony : pour l'aperçu, de façon synchrone puisque la boîte attend ; pour OK ;
- lire avec le compte technique et produire le PDF, avec le code actuel ;
- le remplacer dans l'archive ;
- sur OK, envoyer l'e-mail et passer l'archive « imprimée » (pas d'impression papier, D-011).

Les écritures sont exactement celles d'Armony. La façon dont IFS appellera l'application, et la part du circuit
(`ARMONY_REPORT_JOB`) à garder ou à simplifier, se décident avec l'administrateur IFS (Q12).

## 6. Cas particuliers à couvrir en recette

| Cas | Attendu | Test hors ligne |
|---|---|---|
| Commande planifiée | titre « BROUILLON DE COMMANDE » | `test_commande_planifiee_titree_brouillon` |
| Sans projet | « Projet ou section » et « Numéro projet » vides ; pas de ligne d'adresse projet | `test_ligne_hors_adresse_projet_sans_detail` |
| Lignes article et sans article mêlées | un seul tableau, ordre des n° | `test_lignes_article_et_sans_article_triees_par_numero` |
| Ligne annulée | absente | `test_ligne_annulee_non_imprimee` |
| Frais | après les lignes, dans le total | `test_frais` |
| Cases CGA | les quatre combinaisons de RG-29 | `test_choix_des_cga` |
| Plusieurs versions d'une CGA | la plus récente | `test_cga_la_plus_recente` |
| Société sans logo | pas de logo, pas d'avertissement | `test_societe_sans_logo_dans_ifs_pas_de_logo` |
| Acheteur sans compte technique | document produit, champs de référence vides, avertissements | `test_acheteur_sans_compte_technique_…` |
| Commande d'un autre site | 404 | `test_commande_invisible_pour_l_utilisateur` |
| Commande longue (plusieurs pages) | en-tête de tableau répété, « n/N » juste | à faire sur une vraie commande |
| Devise autre que l'euro | montants des lignes en devise société, frais et prix en devise de la commande, comme Armony | à faire sur une vraie commande |

## 7. Écarts connus avec Armony

| Écart | Raison |
|---|---|
| Mentions et pied de page lus dans un fichier local par société | source OData non identifiée (Q5) ; seul GAE est renseigné |
| Textes document : tous types de sortie | le rapport IFS ne garde que ceux du rapport (Q6) |
| Plusieurs moyens de communication candidats : celui par défaut | Armony gardait le dernier lu |
| SIRET fournisseur : adresse document **de la commande** | Armony : adresse document **par défaut** du fournisseur ; identiques sauf saisie contraire sur la commande |
| Police : Calibri si installée, sinon Carlito (métriques identiques) | sur un serveur Linux, Calibri n'est pas disponible |

## 8. Questions ouvertes

| # | Question | Comment trancher |
|---|---|---|
| Q1 | Quel projet Armony est branché en PROD : `Commande_dachat v1` ou `Commande_dachat_` ? | `CustomProjectionArmonyLayoutConfig` en PROD. Sur CFG, la table pointe le document `9ecc9f74-…`, qui est l'identifiant de `Commande_dachat v1` dans l'export PROD ; l'export REC de la v1 porte un autre identifiant (`3fbe32bb-…`). |
| Q2 | Le total imprimé (`PO_HEADERS.TOTAL_AMOUNT`) est-il `OrderTotalCurr`, `NetAmountCurr + TotalChargeAmountCurr`, ou en devise société ? | comparer `/donnees` et le PDF Armony sur une commande avec frais |
| Q3 | Le rapport IFS imprime-t-il les lignes annulées ? | une commande réelle avec une ligne annulée |
| Q4 | Que contient `PO_HEADERS.NAME`, imprimé après le contact de livraison ? | XML du rapport (archive IFS) ou une commande où il est rempli |
| Q5 | D'où lire en OData les mentions (`DOC_PHRASES`) et le pied de page (`DOCUMENT_FOOTERS`) ? Aucun rôle de CFG n'ouvre `DocumentFooterHandling`. | paramétrage « Phrases sur documents » et « Pied de page de document » d'IFS, avec un administrateur |
| Q6 | Quels types de sortie de texte document le rapport retient-il ? | paramétrage du rapport `PURCHASE_ORDER_PRINT_REP` |
| Q7 | `CompanyFinance.Description` est-elle la raison sociale imprimée (« GA ENTREPRISE SAS ») ? | première lecture réelle |
| Q8 | Un client Keycloak avec utilisateur de service peut-il être créé pour l'application, avec un rôle sur le modèle de `GAIFS_RF_ARMONY` : lectures du § 4, plus les seules écritures du circuit d'impression (archive PDF, travail d'impression, `Cf_EventAction`) ? **Décidé le 30/10/2026 (DSI, D-011)** : oui, un client dans chacun des cinq realms, avec les droits d'Armony ; `ARMONY_SVC` en attendant. | administrateur IFS (création) |
| Q9 | L'identifiant de personne du coordinateur est-il son code (*AuthorizeCode*) ? | première lecture réelle |
| Q10 | ~~La commande personnalisée « ouvrir une URL » de Page Designer accepte-t-elle `${OrderNo}` sur l'écran Commande d'achat en 25R2 ?~~ **Sans objet** : le bouton est retiré (D-011). | – |
| Q11 | ~~Comment le workflow `ARMONY_REPORT_PRVW` et le message `ARMONY_REPORT` atteignent-ils le serveur Armony ?~~ **Répondu le 29/10/2026** : trois appels HTTP vers `ARMONY_SERVER`, § 5.2. | – |
| Q12 | ~~Comment faire appeler l'application à la place d'Armony pour le seul bon de commande, sans toucher aux quatre autres éditiques ? Faut-il garder la recréation du travail d'impression (`ARMONY_REPORT_JOB`) ?~~ **Répondu le 29/10/2026** : `ARMONY_SERVER` pointe vers l'application, qui relaie le reste à Armony pendant les essais (D-009, D-011) ; la recréation du travail est gardée, comme Armony. | – |
| Q13 | Quel serveur SMTP et quelle adresse d'expéditeur pour l'e-mail au fournisseur ? **En partie tranché le 29/10/2026 (Benoit, DSI)** : l'expéditeur est une adresse `@ga.fr` ; sur AWS, l'envoi passe par SES, avec le domaine `ga.fr` vérifié (DKIM, SPF). Reste à choisir l'adresse. Le 30/10/2026 : le SMTP d'Armony, paramétré par le N2 Infra, n'est pas repris (D-011) ; SES ou boîte M365 à trancher. | DSI |
| Q14 | Combien de temps la boîte attend-elle l'aperçu, et que voit l'utilisateur si l'application échoue ? INT-281 a vu un rendu d'IFS appauvri rester dans l'archive quand le rendu n'aboutit pas. | essai sur CFG une fois branché |
| Q15 | Comment IFS porte-t-il plusieurs destinataires et une copie cachée dans le travail d'impression ? L'application ne lit aujourd'hui que `SEND_PDF_TO`, sinon `PDF_EVENT_PARAM_1`. Plusieurs destinataires, copies et copies cachées sont possibles, tous tirés d'IFS (DSI, 30/10/2026). | un travail réel sur CFG avec plusieurs adresses |

**Première vérification en réel** : sur CFG, ouvrir `/commande-achat/<n°>/donnees` pour une commande connue. La
réponse liste chaque appel IFS avec son statut et chaque avertissement : c'est le relevé de ce qui reste à corriger.
