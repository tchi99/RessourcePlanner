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

`LastModifiedDateTime` est le candidat naturel pour une synchronisation incrémentale, mais le support réel de `$filter`, `$orderby`, pagination et les garanties de ce champ doivent être validés sur l'instance avant de figer l'algorithme.

## Authentification OData

Pendant la validation de développement, un compte utilisateur nominatif peut être utilisé temporairement pour accéder au feed OData.

Garde-fous obligatoires :

- aucun mot de passe, cookie, token ou autre credential dans Git;
- aucun credential dans les images Docker;
- aucun credential dans les logs ou routes de statut;
- configuration injectée uniquement par l'environnement/secrets du runtime;
- le compte nominatif est temporaire.

La cible d'exploitation est un **compte de service ERP dédié à RessourcePlanner** avec les permissions minimales de lecture nécessaires.

Le mécanisme HTTP exact utilisé par l'instance pour authentifier OData doit être confirmé par le smoke réel avant d'être figé dans le code.

## Ressources / employés

La même décision s'applique aux futures données organisationnelles Acumatica : les adaptateurs réels devront consommer des sources OData, et non le Contract-Based REST API.

Le feed/vue Employee/User exact, ses champs, sa clé stable et la relation avec l'identité OIDC restent à découvrir dans #232 avant l'implémentation de #256.

## Écart avec le code actuel

Le code actuel contient encore `AcumaticaProjectSource`, conçu historiquement pour le Contract-Based REST API JSON avec bearer token.

Il ne représente plus la cible d'intégration réelle.

La prochaine adaptation projet doit introduire un lecteur OData Atom/XML derrière le `ProjectSourcePort` existant, puis valider le vrai feed dans #207. Le service applicatif de synchronisation et son repository SQL doivent rester indépendants du protocole Acumatica.

## Validation restante

Avant de considérer l'intégration projet réelle terminée :

1. implémenter l'adaptateur OData Atom/XML;
2. tester le parser avec l'échantillon anonymisé;
3. configurer les credentials de développement hors dépôt;
4. effectuer un GET réel de `RP_Projects`;
5. confirmer la sémantique de `ProjectId`;
6. confirmer filtrage, pagination et comportement de `LastModifiedDateTime`;
7. synchroniser vers une base de développement;
8. relancer la synchronisation et confirmer l'idempotence;
9. remplacer le compte nominatif par un compte de service avant exploitation durable.

Refs : #207 #232 #256
