# Acumatica Phase 1 — synchronisation lecture seule des projets

Cette intégration garde une frontière stricte : **Acumatica → FastAPI/Python → SQL → React**. Le navigateur ne communique jamais directement avec Acumatica.

## Contrat utilisé

RessourcePlanner utilise le contract-based REST API Acumatica :

```text
<base_url>/entity/<endpoint>/<version>/<entity>
```

Le nom de l'endpoint, sa version, l'entité Project et les champs sont tous configurables car ils doivent être confirmés sur l'instance réelle.

## Configuration runtime

La synchronisation Acumatica est facultative. Sans les variables ci-dessous, le serveur démarre normalement et `GET /api/v1/integrations/acumatica` retourne `configured=false`.

Variables requises pour activer la source :

```bat
set RESOURCEPLANNER_ACUMATICA_BASE_URL=https://erp.example/Instance
set RESOURCEPLANNER_ACUMATICA_ACCESS_TOKEN=<token bearer runtime>
set RESOURCEPLANNER_ACUMATICA_VERSION=<version de l'endpoint>
```

Variables optionnelles :

```bat
set RESOURCEPLANNER_ACUMATICA_ENDPOINT=Default
set RESOURCEPLANNER_ACUMATICA_PROJECT_ENTITY=Project
set RESOURCEPLANNER_ACUMATICA_PROJECT_NUMBER_FIELD=ProjectID
set RESOURCEPLANNER_ACUMATICA_PROJECT_NAME_FIELD=Description
set RESOURCEPLANNER_ACUMATICA_PROJECT_CLIENT_FIELD=Customer
set RESOURCEPLANNER_ACUMATICA_PROJECT_MANAGER_FIELD=ProjectManager
set RESOURCEPLANNER_ACUMATICA_PROJECT_STATUS_FIELD=Status
set RESOURCEPLANNER_ACUMATICA_PAGE_SIZE=200
set RESOURCEPLANNER_ACUMATICA_TIMEOUT_SECONDS=30
```

Le token n'est jamais enregistré dans SQL, renvoyé par les routes de statut ou inclus dans les erreurs applicatives. Cette première tranche accepte un bearer token fourni par l'environnement; l'obtention/renouvellement OAuth/OIDC sera branchée derrière la même frontière lorsque les paramètres de l'instance seront disponibles.

Une configuration Acumatica partielle fait échouer explicitement le démarrage afin d'éviter un serveur qui semble synchroniser alors qu'il manque un secret, l'URL ou la version de contrat.

## Routes

Statut non sensible :

```text
GET /api/v1/integrations/acumatica
```

Synchronisation manuelle :

```text
POST /api/v1/integrations/acumatica/projects/sync
```

Sans source configurée, la synchronisation retourne `503 acumatica_not_configured`.

Résultat typique :

```json
{
  "received": 25,
  "created": 3,
  "updated": 4,
  "unchanged": 18
}
```

## Sémantique de synchronisation

- résolution prioritaire par `erp_external_id`;
- rapprochement par numéro uniquement pour adopter un projet historique sans ID ERP;
- conflit explicite si le numéro local est déjà lié à un autre ID ERP;
- mise à jour du numéro, nom, client, chargé de projet et statut depuis l'ERP;
- aucune suppression locale basée sur l'absence d'un projet dans une réponse;
- un projet explicitement retourné comme inactif reste en SQL avec son historique et son nouveau statut;
- rejouer exactement la même synchronisation produit uniquement des `unchanged`.

## Validation réelle restant à faire

Quand l'accès à l'instance Acumatica sera disponible :

1. confirmer l'URL d'instance;
2. confirmer l'endpoint et sa version sur `SM207060`;
3. vérifier l'entité qui représente les projets;
4. vérifier les noms de champs exposés par le contrat ou son `swagger.json`;
5. obtenir un token de test selon le mécanisme OAuth/OIDC retenu;
6. appeler la route de statut puis lancer une synchronisation sur une base de développement;
7. réconcilier quelques projets connus avant toute utilisation en production.


## Readiness locale avant accès réel

Les comportements de résilience (pagination, erreurs réseau/HTTP, payloads invalides, atomicité, métriques et journalisation sûre) sont détaillés dans [V2_ACUMATICA_READINESS.md](V2_ACUMATICA_READINESS.md).

Cette validation ne confirme pas le contrat réel de l'instance. Les noms d'entités/champs, la pagination réellement supportée, les statuts, Employee/User, OIDC et l'embedding restent à confirmer dans #232 et les smokes associés.
