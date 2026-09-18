# Catalogue de tâches ERP — import temporaire

Cette intégration est la source transitoire du catalogue de tâches de RessourcePlanner tant que
l'accès direct à Acumatica n'est pas disponible.

## Identité autoritaire

L'export réel confirme que **ID tâche n'est pas unique globalement**. Un même code (par exemple
`210`) peut avoir un libellé différent selon le projet.

La clé métier du catalogue est donc :

```text
(ID projet, ID tâche)
```

Le libellé n'est jamais utilisé comme identifiant. La future source Acumatica devra produire le
même contrat `TaskCatalogItem`; l'API et React n'auront pas à changer de source.

## Colonnes de l'export ERP

Colonnes requises :

| Colonne ERP | Champ RessourcePlanner | Usage |
| --- | --- | --- |
| `ID projet` | `project_number` | Première partie de la clé autoritaire |
| `ID tâche` | `code` | Deuxième partie de la clé autoritaire |
| `Description` | `label` | Libellé affiché aux utilisateurs |
| `Statut` | `status` / `active` | Contrôle si la tâche est sélectionnable |

Métadonnées conservées lorsqu'elles sont présentes :

| Colonne ERP | Champ |
| --- | --- |
| `Règle de facturation` | `billing_rule` |
| `Règle de répartition` | `allocation_rule` |
| `Complété (%)` | `completion_percent` |
| `Créé le` | `erp_created_at` |
| `Succursale` | `branch` |
| `Nom de l’employé` | `approver_name` |
| `CV` | `cv_enabled` |
| `Saisie des heures` | `time_entry_enabled` |
| `Dépenses` | `expenses_enabled` |

La colonne `Sélectionné` de l'export n'est pas une donnée de référence et n'est pas importée.

## Formats acceptés

- XLSX / XLSM : feuille `Données`;
- CSV : séparateur virgule, point-virgule ou tabulation; UTF-8 avec BOM et Windows-1252 sont pris
  en charge.

Une ligne sans projet, code ou description est rejetée. Un doublon de la clé
`(ID projet, ID tâche)` est rejeté. Le même `ID tâche` sous deux projets différents est valide.

Un statut `Actif`/ `Active` rend la tâche sélectionnable. Un statut explicitement inactif est
conservé dans le catalogue mais n'est plus proposé pour une nouvelle demande. L'import ne déduit
pas une désactivation de la simple absence d'une ligne, afin qu'un export partiel ne puisse pas
désactiver des données silencieusement.

## Import Docker

Prévisualisation, sans écriture :

```bash
docker compose run --rm import-tasks "/imports/Tâches de projet.xlsx"
```

Application :

```bash
docker compose run --rm import-tasks "/imports/Tâches de projet.xlsx" --apply
```

Le même service accepte un fichier CSV.

## API

Recherche dans le catalogue :

```http
GET /api/v1/task-catalog?project_number=5176&q=automatisation&active_only=true
```

React utilise cette API. La demande enregistre le code et le libellé sélectionnés comme snapshot
historique, tandis que la validation d'une nouvelle sélection se fait toujours contre la clé
`(projet, code)` active du catalogue.
