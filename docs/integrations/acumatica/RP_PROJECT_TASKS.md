# Acumatica — contrat RP_ProjectTasks

## Décision produit

`RP_ProjectTasks` devient la source OData cible du catalogue de tâches projet et des informations de budget associées.

Le fallback Excel/CSV livré dans #271 reste disponible uniquement tant que l'adaptateur OData n'est pas livré et validé.

Le volume observé par le PO impose une stratégie de synchronisation **ciblée et mise en cache**. Le runtime ne doit pas relire le feed complet à chaque consultation de l'application.

## Feed

Chemin :

```text
/oDATA/RP_ProjectTasks
```

Requête utilisée pour produire l'échantillon anonymisé :

```text
/oDATA/RP_ProjectTasks?$top=1000&$filter=Status eq 'Actif'
```

Le PO a observé environ **41 073 entrées** lorsque le feed est interrogé sans filtre. Cette valeur est une observation de l'instance au 2026-09-25, pas une constante de contrat.

Format observé : OData Atom/XML.

Type d'entité :

```text
PX.Data.RP_ProjectTasks
```

Fixture anonymisée :

```text
tests/fixtures/acumatica/rp_project_tasks_atom.xml
```

## Champs observés

| Champ OData | Type observé | Sémantique / usage |
| --- | --- | --- |
| `ProjetCD` | string paddée | numéro/code projet descriptif |
| `TaskCD` | string paddée | code tâche métier |
| `AccountGroup` | string paddée | groupe de compte du budget |
| `ProjetID` | `Edm.Int32` | identifiant projet candidat |
| `TaskID` | `Edm.Int32` | identifiant tâche candidat |
| `TaskDescription` | string | libellé tâche |
| `Status` | string | état tâche; `Actif` observé |
| `StartDate` | `Edm.DateTime` | début |
| `EndDate` | `Edm.DateTime` / null | fin |
| `PlannedEndDate` | `Edm.DateTime` / null | fin planifiée |
| `Type` | string | type de tâche |
| `BudgetAmount` | `Edm.Decimal` | montant budgétaire de la ligne |
| `BudgetActual` | `Edm.Decimal` | réalisé budgétaire de la ligne |
| `BaseType` | string | type de base ERP |
| `ProjectID` | string paddée | code/identité projet ERP descriptive |
| `ProjectID_2` | `Edm.Int32` | identifiant projet candidat; correspond aux valeurs projet numériques observées |
| `ProjectTaskID` | `Edm.Int32` | identifiant technique candidat de tâche projet |
| `CostCode` | string | code coût |
| `InventoryID` | string paddée | article/inventaire ou `<N/A>` |

Les chaînes paddées doivent être normalisées avec `strip()` lorsqu'elles servent de codes/identifiants.

Les montants doivent rester des `Decimal`; ne pas les convertir en `float`.

## Granularité du feed

L'identifiant Atom observé contient plusieurs dimensions :

- `ProjetCD`;
- `TaskCD`;
- `AccountGroup`;
- `BaseType`;
- `ProjectID`;
- `ProjectID_2`;
- `ProjectTaskID`;
- `CostCode`;
- `InventoryID`.

Cela signifie que RessourcePlanner ne doit **pas supposer qu'une entrée OData = une tâche unique**.

Le feed ressemble à une projection tâche + ligne de budget/dimension comptable. Plusieurs entrées peuvent donc potentiellement représenter la même tâche avec des groupes de compte, codes coût ou articles différents.

L'implémentation doit séparer :

```text
Task identity / metadata
        │
        └── 0..N budget lines
```

Ne pas créer plusieurs `TaskCatalogEntry` uniquement parce que plusieurs lignes budgétaires existent.

## Identité tâche — point à confirmer

Le catalogue actuel RessourcePlanner utilise comme identité durable :

```text
(project_number, task_code)
```

Le feed expose aussi `TaskID` et `ProjectTaskID`, qui sont des candidats à une clé technique ERP plus robuste.

Avant de changer l'identité SQL du catalogue, confirmer côté PO :

1. si `ProjectTaskID` est unique et stable à l'échelle de l'instance;
2. si `TaskID` et `ProjectTaskID` sont toujours équivalents;
3. si `ProjectID_2` correspond exactement à `RP_Projects.ProjectId`.

Tant que cette confirmation n'est pas faite, ne pas introduire de migration destructive d'identité.

## Budgets

Le sample montre que :

- `BudgetAmount` et `BudgetActual` sont des décimaux monétaires/quantitatifs ERP dont l'unité exacte reste à confirmer;
- un budget peut être négatif;
- le réalisé peut dépasser le budget;
- `AccountGroup`, `CostCode` et `InventoryID` font partie de la granularité observée.

Conséquences :

- ne jamais clamp les valeurs à zéro;
- ne pas mapper `BudgetAmount` vers `planned_hours` ou un effort Planning;
- ne pas sommer indistinctement coûts et revenus avant confirmation de la sémantique métier des groupes de compte;
- conserver au besoin les lignes budgétaires séparées, puis produire des agrégats explicites par catégorie lorsque les règles métier sont connues.

## Performance et stratégie de synchronisation

### Interdit

Ne pas :

- charger les ~41k lignes à chaque ouverture de l'application;
- appeler Acumatica à chaque rendu de dropdown;
- utiliser uniquement `$top=1000` comme pseudo-pagination;
- considérer l'absence d'une tâche dans un résultat filtré `Status eq 'Actif'` comme une preuve de désactivation;
- exécuter une synchronisation complète en boucle courte.

### Stratégie cible

Le catalogue local SQL reste la source de lecture du frontend.

La synchronisation OData doit être **ciblée par projet** et mise en cache.

Flux recommandé :

```text
Utilisateur ouvre/sélectionne un projet
        ↓
catalogue local disponible immédiatement
        ↓
si snapshot du projet absent ou expiré
        ↓
refresh OData ciblé du projet
        ↓
upsert transactionnel local
        ↓
nouveau last_synced_at projet
```

Pour un refresh projet, préférer un snapshot de **toutes les tâches du projet**, et non uniquement `Status eq 'Actif'`, afin que les passages Actif → Inactif puissent être observés explicitement sans interpréter une absence d'un résultat partiel.

La syntaxe de filtre projet doit être validée contre l'instance avant implémentation. Le candidat naturel est l'identifiant numérique lié à `RP_Projects.ProjectId`.

### Cache

Prévoir un état de synchronisation par projet, par exemple :

- dernier succès;
- dernière tentative;
- dernière erreur;
- nombre de lignes reçues;
- nombre de tâches agrégées;
- durée;
- statut stale/fresh.

Le TTL doit être configurable. Pour le bootstrap/test initial, une valeur prudente telle que **24 h** avec bouton ADMIN « Rafraîchir maintenant » est acceptable; ne pas figer ce nombre comme contrainte métier durable.

### Pagination

Même avec un filtre projet, l'adaptateur doit supporter plusieurs pages.

Valider sur `RP_ProjectTasks` :

- `$orderby`;
- `$top`;
- `$skip`;
- absence/présence d'un `rel="next"`;
- limite maximale de page.

Utiliser un ordre déterministe. Ne pas supposer que les capacités déjà validées sur `RP_Projects` sont identiques avant smoke réel.

## Incrémentalité

Le sample ne contient pas de propriété métier `LastModifiedDateTime`.

Le champ Atom `<updated>` observé ne doit pas être traité comme un curseur métier fiable sans validation explicite.

En l'absence de curseur incrémental fiable, préférer :

- refresh ciblé par projet;
- TTL/cache;
- refresh manuel ADMIN;
- éventuellement une réconciliation périodique des projets réellement utilisés.

Éviter un polling global fréquent.

## Intégration avec #271 / #447

Le modèle durable de catalogue #271 doit être réutilisé.

La future source :

```text
ODataProjectTaskSource
        ↓
TaskCatalogSourcePort
        ↓
TaskCatalogSyncService
        ↓
TaskCatalogRepository
```

peut remplacer le fallback fichier sans changer les consommateurs.

Cependant, le contrat actuel `TaskCatalogSourcePort.list_tasks()` représente un snapshot global et le service rejette les doublons `(project_number, task_code)`. Pour `RP_ProjectTasks`, une extension ciblée par projet et une étape d'agrégation des lignes budgétaires seront probablement nécessaires.

Ne pas faire passer les lignes budgétaires brutes directement dans le service actuel comme autant de tâches.

## Questions PO encore ouvertes

Avant implémentation complète :

1. confirmer que `ProjectTaskID` est une clé unique/stable de tâche;
2. confirmer le lien exact `ProjectID_2` ↔ `RP_Projects.ProjectId`;
3. préciser l'unité/devise de `BudgetAmount` et `BudgetActual`;
4. préciser si les budgets coût et revenu doivent être présentés séparément par `AccountGroup`;
5. valider une requête OData ciblée sur **un seul projet**;
6. valider pagination/ordre sur ce feed;
7. déterminer si un champ LastModified fiable peut être ajouté à la vue OData.

## Références

- #271 — catalogue tâches
- #232 — contrat Acumatica
- #447 — bootstrap données réalistes
- [ACUMATICA_ODATA_CONTRACT.md](../../ACUMATICA_ODATA_CONTRACT.md)
- [ACUMATICA_CONTRACT_WORKFLOW.md](../../ACUMATICA_CONTRACT_WORKFLOW.md)
