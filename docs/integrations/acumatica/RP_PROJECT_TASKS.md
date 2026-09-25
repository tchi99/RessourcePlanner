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

## Identité tâche et relation projet

Décisions PO confirmées :

```text
RP_ProjectTasks.TaskID = clé unique/stable de la tâche ERP
trim(RP_ProjectTasks.ProjectCD) = RP_Projects.ProjectCode
```

`ProjectID_2` est le numéro interne ERP du projet, mais RessourcePlanner utilise `ProjectCD → ProjectCode` comme relation métier autoritaire pour ce contrat.

L'identifiant Atom expose plusieurs colonnes techniques de la vue OData, mais ces colonnes ne remplacent pas `TaskID` comme identité fonctionnelle de la tâche.

Le catalogue #271 utilise actuellement `(project_number, task_code)`. La transition OData doit donc ajouter un identifiant ERP `TaskID` nullable/stable sans casser les références historiques issues du fallback fichier.

## Budgets

Décision PO confirmée :

- `BudgetAmount` est un montant monétaire en **CAD**;
- `BudgetActual` est un montant monétaire réalisé en **CAD**;
- un budget peut être négatif;
- le réalisé peut dépasser le budget.

Les montants restent des `Decimal`.

### Conversion budget → heures workforce

Pour les tâches associées à une classe de ressource, RessourcePlanner calcule une projection d'heures à partir du coût horaire moyen administré pour la classe :

```text
budget_hours = BudgetAmount_CAD / average_hourly_cost_CAD
```

Cette projection n'est pas un actual d'heures et ne doit jamais être confondue avec un Shift ou une ligne approuvée.

`BudgetActual` demeure un montant CAD réel. Il ne devient pas automatiquement un nombre d'heures autoritaire.

Si le coût est absent/0 ou si le budget produit une valeur incohérente pour Planning, le système doit afficher un diagnostic plutôt que fabriquer silencieusement un effort valide.

Voir #454.

## Classification workforce et import ciblé

Le produit ne doit pas importer/configurer manuellement toutes les tâches de tous les projets.

Un référentiel ADMIN séparé (#454) fournit :

- les classes de ressources;
- un coût horaire moyen CAD par classe;
- les standards globaux `TaskCD → classe`;
- les exceptions par projet.

Exemples initiaux :

```text
117 → Installateur électrique
216 → Programmeur
217 → Installateur automatisation
```

Ces correspondances sont administrables et **ne sont pas codées en dur**.

Résolution :

```text
override projet
    ↓ si présent
classe spécifique / EXCLUDE
    ↓ sinon
standard TaskCD
    ↓ sinon
non classé
```

Pour un projet ciblé, l'adaptateur peut récupérer les tâches du projet puis ne conserver dans le catalogue workforce que celles ayant une classe effective. Cela évite de charger le feed global tout en laissant les exceptions projet possibles.

Cette classification workforce reste distincte des `ApprovalScope` de #276/ADR-010. Une même autorité d'approbation peut couvrir plusieurs classes de ressources différentes.

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

## Questions encore ouvertes

Avant implémentation complète :

1. valider une requête OData ciblée sur **un seul projet** via `ProjectCD`;
2. valider `$orderby=TaskID asc`, `$top/$skip` et la présence éventuelle de `rel=next`;
3. déterminer si un champ LastModified fiable peut être ajouté à la vue OData;
4. confirmer si certains TaskCD workforce peuvent contenir des montants autres que de la main-d'œuvre nécessitant une règle supplémentaire sur `AccountGroup`;
5. définir les valeurs initiales des coûts moyens par classe et la liste initiale des standards TaskCD dans #454.

## Références

- #271 — catalogue tâches
- #232 — contrat Acumatica
- #447 — bootstrap données réalistes
- [ACUMATICA_ODATA_CONTRACT.md](../../ACUMATICA_ODATA_CONTRACT.md)
- [ACUMATICA_CONTRACT_WORKFLOW.md](../../ACUMATICA_CONTRACT_WORKFLOW.md)
