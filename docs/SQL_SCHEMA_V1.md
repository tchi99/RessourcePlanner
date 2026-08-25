# Schéma SQL V1 — fondation de migration

Ce document décrit la première cible relationnelle de RessourcePlanner. Le schéma est volontairement indépendant de PostgreSQL ou SQL Server : le choix du moteur et du driver reste un détail de déploiement.

## Principes d'identité

Chaque entité SQL possède un `id` interne stable, généré indépendamment d'Excel et d'Acumatica. Les identifiants externes sont conservés dans des colonnes distinctes (`erp_external_id`, `external_id`, `legacy_*`).

Les identifiants externes/legacy optionnels sont indexés mais ne sont pas déclarés `UNIQUE` dans cette première migration. La sémantique des index uniques nullable diffère notamment entre PostgreSQL et SQL Server; la déduplication sera donc contrôlée par les futurs adaptateurs de synchronisation/migration tant que ces colonnes demeurent optionnelles.

## Hiérarchie métier cible

Flux normal :

```text
Project
  → WorkPackage
    → WorkforceRequest
      → ResourceRequirement
        → Shift
```

Flux ad hoc / Quick Shift :

```text
Project
  → ResourceRequirement [QUICK_SHIFT / AD_HOC]
    → Shift
```

Un Quick Shift ne crée **jamais** de fausse demande de main-d'œuvre.

## Nullabilités structurantes

### `resource_requirements.project_id`

`NOT NULL` par design. Tout besoin de ressource doit toujours être rattaché à un projet, y compris un Quick Shift.

### `resource_requirements.workforce_request_id`

Nullable **de façon permanente**. Cette nullabilité représente explicitement les besoins ad hoc/Quick Shift. Une contrainte exige que l'absence de demande soit accompagnée d'une origine `QUICK_SHIFT` ou `AD_HOC`.

### `workforce_requests.work_package_id`

Nullable **temporairement pour la migration V1**. L'application Excel actuelle possède des demandes créées avant l'introduction de WorkPackage; la migration ne doit pas fabriquer de faux WorkPackages uniquement pour satisfaire une FK.

Les nouveaux workflows serveur pourront rendre le WorkPackage obligatoire au niveau applicatif une fois la migration historique complétée. Une future migration SQL pourra ensuite rendre la colonne `NOT NULL` si les données le permettent.

## Mapping des sources Excel

| Source V1 | Table SQL | Identité legacy | Notes |
| --- | --- | --- | --- |
| `Liste_Projet` / source ERP projet | `projects` | numéro + futur `erp_external_id` | Acumatica deviendra la source de vérité projet/PM. |
| `Liste_Effort` | `work_packages` | `IDEffort` → `legacy_effort_id` | Le mapping exact effort → WorkPackage sera validé pendant la migration de données. |
| `DemandesMO` | `workforce_requests` | `NoDemande` → `legacy_demand_number` | `work_package_id` peut rester vide pour l'historique V1. |
| `Historique` | `workforce_request_history` | référence demande | Historique d'actions/statuts, pas une copie courante de la demande. |
| `RessourcesMO` | `resources` | futur `external_id` | `resource_class`, actif et ordre manuel sont conservés. |
| `Disponibilites` | `resource_availability_rules` | `ID` → `legacy_id` | Horaire standard, vacances, jours fériés et règles datées. |
| `SegmentsMO` | `resource_requirements` | `IDSegment` → `legacy_segment_id` | `NoDemande` devient FK nullable; `OrigineSegment=QUICK_SHIFT` reste ad hoc. |
| `AllocationsMO` | `shifts` | `IDAllocation` → `legacy_allocation_id` | Les quarts verrouillés restent des lignes `locked=true` persistantes. |

## Mapping principal des colonnes

### DemandesMO → workforce_requests

- `NoDemande` → `legacy_demand_number`
- `NumeroProjet` → résolution vers `project_id`
- futur WorkPackage → `work_package_id`
- `Demandeur` → `requester_name` / futur `requester_external_id`
- `TypeDemande` → `request_type`
- `Priorite` → `priority`
- `Confirmation` → `confirmation`
- `DateDebutSouhaitee` / `DateFinSouhaitee` → `desired_start` / `desired_end`
- `Description`, `SiteClient`, `Lieu`
- `NombreRessources` → `resource_count`
- `CompetencesRequises` → `required_competencies`
- `TempsEstimeHeures` / `TempsEstimeJours`
- `TechnicienPropose` → résolution vers `proposed_resource_id`
- `Statut` → `status`
- approbation → `approved_*`

### SegmentsMO → resource_requirements

- `IDSegment` → `legacy_segment_id`
- `NumeroProjet` → résolution vers `project_id`
- `NoDemande` → résolution vers `workforce_request_id`, nullable pour ad hoc
- `Technicien` → résolution vers `assigned_resource_id`
- `DateDebut` / `DateFin` → `start_date` / `end_date`
- `HeuresPrevues` → `planned_hours`
- `Statut`, `Description`
- `SourceEffortID` → `source_effort_id`
- `CompetenceRequise` → `required_competency`
- `TypePlanification` → `planning_type`
- `Priorite` → `priority`
- `HorsHoraireAutorise` → `outside_standard_hours_allowed`
- `OrigineSegment` → `origin`

### AllocationsMO → shifts

- `IDAllocation` → `legacy_allocation_id`
- `IDSegment` → résolution vers `resource_requirement_id`
- `Technicien` → résolution vers `resource_id`
- `Date` → `work_date`
- `Heures` → `hours`
- `TypeAllocation` → `allocation_type`
- génération automatique/manuelle → `source`
- `Verrouillee` → `locked`
- `HorsHoraire` → `outside_standard_hours`
- confirmation → `confirmation`
- `Note` → `note`

## Données hors de cette première migration

Les éléments suivants seront modélisés lorsqu'un consommateur stable l'exigera :

- utilisateurs locaux et rôles RessourcePlanner;
- registres/snapshots de communication;
- paramètres et préférences locales;
- données financières Acumatica (budgets, coûts, réels);
- journal technique de synchronisation ERP.

## Étapes suivantes

1. Valider le schéma/migration initiale sur SQLite et compiler le DDL pour PostgreSQL/MSSQL.
2. Implémenter les adaptateurs SQL des ports applicatifs.
3. Construire l'import/migration Excel → SQL avec rapports de réconciliation.
4. Rendre SQL autoritaire seulement après comparaison complète avec la V1 Excel.
5. Ajouter FastAPI au-dessus de `app.application.ApplicationFacade`.
