# Acumatica — contrat OData cible

## Décision d'intégration

RessourcePlanner n'utilisera pas le **Contract-Based REST API** d'Acumatica pour ses synchronisations métier.

La direction retenue est :

```text
Acumatica OData
    ↓
adaptateurs Python
    ↓
ports applicatifs
    ↓
services de synchronisation
    ↓
SQL
```

Le navigateur React ne communique jamais directement avec Acumatica.

L'authentification OIDC des utilisateurs, lorsqu'elle est utilisée, reste un sujet distinct du protocole OData servant à lire les données ERP.

## Projets — RP_Projects

La vue OData cible pour les projets est :

```text
/oDATA/RP_Projects
```

Le nom d'hôte réel de l'ERP est une donnée d'environnement et n'est pas commité dans ce dépôt public.

Le flux observé est un feed **OData Atom/XML** avec notamment :

- namespace Atom;
- namespace `d` pour les propriétés;
- namespace `m` pour les métadonnées;
- entité `PX.Data.RP_Projects`;
- valeurs nulles via `m:null="true"`;
- chaînes pouvant contenir des espaces significatifs via `xml:space="preserve"`;
- dates typées `Edm.DateTime`.

Un échantillon anonymisé fidèle au contrat réel a été fourni pour guider l'implémentation et les tests.

## Identité projet

La clé externe stable retenue pour RessourcePlanner est :

```text
Project.erp_external_id = RP_Projects.ProjectId
```

`ProjectId` est l'identifiant unique du projet dans la base Acumatica.

`ProjectCode` n'est **pas** la clé technique : il correspond au numéro de projet utilisé à l'interne et doit rester la valeur métier affichée/recherchée.

Les URI Atom `self` / `edit` peuvent exposer d'autres composantes de clé OData, mais RessourcePlanner ne doit pas en déduire son identité métier tant que `ProjectId` est disponible comme identifiant stable Acumatica.

## Mapping RP_Projects → RessourcePlanner

| RP_Projects | Sémantique | Cible RessourcePlanner |
| --- | --- | --- |
| `ProjectId` | clé DB Acumatica unique | `erp_external_id` / identité externe stable |
| `ProjectCode` | numéro de projet interne | numéro de projet |
| `ProjectName` | nom/description du projet | nom |
| `CustomerID` | identifiant client ERP | donnée ERP descriptive/référence si utile |
| `CustomerName` | nom du client | client |
| `ProjectManagerId` | identifiant ERP du chargé de projet | référence externe lorsque le contrat identité sera stabilisé |
| `ProjectManagerName` | nom affiché du chargé de projet | chargé de projet descriptif |
| `Status` | statut ERP | statut projet |
| `StartDate` | date de début | date de début si utilisée |
| `EndDate` | date de fin nullable | date de fin si utilisée |
| `DefaultBranchCode` | division | code de division |
| `DefaultBranchCode_Desc` | libellé de division | libellé descriptif |
| `LastModifiedDateTime` | dernière modification ERP | candidat pour synchro incrémentale |
| `BaseType` | type ERP du projet | classification ERP; règle de filtrage à confirmer |

## Divisions

Le mapping métier connu de `DefaultBranchCode` est :

| Code | Division |
| --- | --- |
| `110` | Électrique |
| `210` | Automatisation |
| `310` | Excavation |
| `510` | Mécanique industrielle |
| `910` | Interne |

Les codes présents dans l'échantillon anonymisé ne doivent pas être interprétés comme le mapping de production.

## Normalisation du feed

L'adaptateur OData devra au minimum :

- parser Atom/XML sans dépendre des préfixes exacts, mais selon les namespaces;
- convertir `m:null="true"` en `None`;
- appliquer `strip()` aux identifiants/codes textuels susceptibles d'être paddés;
- préserver correctement Unicode et caractères accentués;
- convertir les `Edm.DateTime` en valeurs temporelles Python cohérentes;
- exiger `ProjectId`, `ProjectCode` et `ProjectName` pour un projet exploitable;
- ne jamais utiliser le nom du projet ou du chargé de projet comme clé d'identité.

## Statuts

L'échantillon anonymisé couvre notamment :

- `Actif`;
- `En planification`;
- `Complété`;
- `Suspendu`;
- `Annulé`.

Ces valeurs servent au contrat de parsing. La liste exhaustive et les règles exactes d'admissibilité à la synchronisation doivent être confirmées contre le flux réel.

## Synchronisation

La sémantique applicative existante reste souhaitée :

- lecture Acumatica en lecture seule;
- rapprochement prioritaire par `ProjectId`;
- mise à jour idempotente;
- absence d'un projet dans un pull ≠ suppression/inactivation locale implicite;
- statut explicitement retourné par Acumatica peut mettre à jour le projet local;
- transaction SQL atomique pour l'application d'un snapshot;
- aucune donnée métier sensible dans les logs.

`LastModifiedDateTime` reste un candidat pour une future synchronisation incrémentale. Le smoke réel du 2026-09-24 a confirmé qu'il est exposé comme `Edm.DateTime`, filtrable avec des littéraux `datetime'YYYY-MM-DDTHH:MM:SS[.fff]'` (`eq`, `ge`, `gt`) et utilisable avec `$orderby`. L'heure OData observée était quatre heures en avance sur l'interface Acumatica au Québec (13:56 OData contre 09:56 UI), cohérente avec UTC versus EDT ce jour-là. Cette observation ne suffit pas à figer un algorithme incrémental ni une garantie générale de timezone.

Le même smoke a confirmé `$filter` sur `ProjectId` et `ProjectCode`, ainsi qu'une pagination déterministe par `$orderby=ProjectId asc`, `$top` et `$skip`. Trois fenêtres successives de cinq projets ont produit trois groupes distincts et aucun lien Atom `rel="next"` n'a été observé. La limite maximale acceptée par le serveur n'a pas été mesurée; le client utilise donc une taille de page configurable et accumule toutes les pages avant de remettre le snapshot au service applicatif.

## Authentification OData

Pendant la validation de développement, un compte utilisateur nominatif peut être utilisé temporairement pour accéder au feed OData.

Garde-fous obligatoires :

- aucun mot de passe, cookie, token ou autre credential dans Git;
- aucun credential dans les images Docker;
- aucun credential dans les logs ou routes de statut;
- configuration injectée uniquement par l'environnement/secrets du runtime;
- le compte nominatif est temporaire.

La cible d'exploitation est un **compte de service ERP dédié à RessourcePlanner** avec les permissions minimales de lecture nécessaires.

Le smoke réel du 2026-09-24 a confirmé **HTTP Basic** sur cette instance. Le runtime utilise un username et un mot de passe injectés uniquement par l'environnement/secrets; aucun credential ni hostname réel n'est exposé par les diagnostics sûrs. Le compte nominatif utilisé pour le smoke reste temporaire et doit être remplacé par un compte de service dédié avant exploitation durable.

## Ressources / employés

La même décision s'applique aux futures données organisationnelles Acumatica : les adaptateurs réels devront consommer des sources OData, et non le Contract-Based REST API.

Le développement Employees/Users suit désormais un modèle **contract-first sans accès ERP développeur**. Le PO/opérateur autorisé valide la vue OData réelle, puis fournit au dépôt uniquement le contrat nécessaire et un échantillon entièrement anonymisé mais structurellement fidèle. Le développeur implémente ensuite l'adaptateur et ses tests contre ce contrat local; le smoke réel est exécuté séparément par le PO/opérateur autorisé.

Le feed/vue Employee/User exact, ses champs, sa clé stable et la relation avec l'identité OIDC restent à fournir dans #232 avant l'implémentation de #256. L'accès direct à Acumatica par le développeur n'est pas un prérequis.

Voir [ACUMATICA_CONTRACT_WORKFLOW.md](ACUMATICA_CONTRACT_WORKFLOW.md).

### Statut contractuel Employee/User

Au 2026-09-25, aucun contrat OData Employee/User/ressource n'a encore été fourni au dépôt sous la forme validée attendue par #232. Les seules observations ERP réelles déjà stabilisées dans le dépôt concernent `RP_Projects`.

En conséquence :

- un nom historique ou proposé comme `RP_Employees` n'est **pas** un contrat tant que le PO/opérateur autorisé ne l'a pas validé dans Acumatica et transmis sous forme désensibilisée;
- aucun champ supposé (`EmployeeID`, `UserID` ou équivalent) ne doit être déclaré clé externe stable sans contrat validé;
- aucune règle de planifiabilité ne doit être dérivée d'un nom de champ supposé;
- aucune jointure User ↔ Employee par nom ou courriel n'est autoritaire;
- les capacités démontrées pour `RP_Projects` (`$filter`, `$orderby`, `$top/$skip`, `LastModifiedDateTime`) ne sont pas automatiquement transposées au futur feed Employee.

La reprise de #232 doit donc commencer par une validation du feed côté PO/opérateur autorisé, puis par la transmission au développeur du **contrat + fixture anonymisée structurellement fidèle**. Le développeur n'a pas besoin d'accéder à l'ERP réel; il implémente ensuite #256 contre ce contrat local et la CI reste indépendante d'Acumatica.

## Outillage contractuel local

Les enveloppes Atom/OData communes sont centralisées dans `app/infrastructure/acumatica/odata_atom.py`. Cette primitive couvre uniquement la structure commune réellement réutilisable : namespaces Atom/`d`/`m`, `m:properties`, `m:null`, type `m:type`, `xml:space`, métadonnées d'entité/liens et classification HTTP stable.

Elle ne porte ni mapping métier, ni clé d'entité, ni pagination générique. `ODataProjectSource` conserve donc ses règles propres à `RP_Projects`.

Les contrats anonymisés peuvent être inspectés sans réseau avec :

```bash
python tools/inspect_odata_contract.py <sample.xml>
```

Le workflow complet et le template de nouveau contrat sont documentés dans `ACUMATICA_CONTRACT_WORKFLOW.md` et `docs/integrations/acumatica/CONTRACT_TEMPLATE.md`.

## Implémentation locale

Le runtime projet compose `ODataProjectSource`, un lecteur Atom/XML dédié derrière le `ProjectSourcePort` existant. `ProjectId`, `ProjectCode`, `ProjectName`, client, chargé de projet et statut sont projetés vers `ExternalProjectRecord` sans modifier `ProjectSyncService`.

`StartDate`, `EndDate`, `DefaultBranchCode`, `DefaultBranchCode_Desc`, `LastModifiedDateTime`, `CustomerID` et `BaseType` sont parsés dans le record d'infrastructure mais ne sont pas ajoutés au modèle SQL `Project`. Les valeurs `BaseType` observées sur l'instance sont `P` et `R`; les entrées `R` semblent correspondre à des templates. Cette interprétation reste à confirmer fonctionnellement et aucune règle de filtrage `BaseType` n'est appliquée dans #207B.

L'ancien `AcumaticaProjectSource` REST/JSON reste présent uniquement comme compatibilité historique; il n'est plus le chemin composé par le runtime projet.

## Validation restante

#207 est terminé. Le smoke réel du 2026-09-24 et la synchronisation de développement ont confirmé :

1. HTTP Basic avec credentials hors dépôt;
2. GET réel de `RP_Projects` en Atom/XML;
3. `ProjectId` comme identité stable et `ProjectCode` comme numéro métier;
4. `$filter`, `$orderby`, pagination `$top/$skip` sans `rel="next"`, et le comportement décrit ci-dessus de `LastModifiedDateTime`;
5. une première synchronisation de 1286 projets puis un replay idempotent avec 1286 entrées inchangées, sans doublon ni suppression locale implicite.

La signification métier exacte de `BaseType=R` et le remplacement du compte nominatif par un compte de service restent des sujets séparés du contrat projet livré; ils ne rouvrent pas #207.

La validation encore structurante pour les ressources est le **contract gate #232** : feed Employee/User validé par le PO, clé externe stable, admissibilité à la planification, relation User ↔ Employee, capacités de synchronisation propres à ce feed et fixture anonymisée fidèle. Une fois ce paquet fourni, #256 peut être développé sans accès ERP direct.

Refs : #207 #232 #256
