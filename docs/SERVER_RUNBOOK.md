# Runbook — backend FastAPI / SQL

Ce document décrit le runtime serveur de RessourcePlanner introduit par SQL 4 / API 1. Il est volontairement séparé du runtime NiceGUI/Excel historique : le backend FastAPI ne démarre ni Excel, ni NiceGUI, ni les installateurs V1.x.

## État actuel

La couche serveur est prête à être configurée et lancée avec `python -m app.server`.

La validation finale sur le futur environnement virtuel et le driver SQL Server réel reste à faire avant de déclarer ce runtime prêt pour la production. Tant que l'authentification Acumatica/OIDC n'est pas ajoutée, ne pas exposer l'API sur un réseau non maîtrisé.

## 1. Dépendances Python

Depuis la racine du dépôt :

```bat
python -m pip install -r requirements.txt
```

FastAPI et Uvicorn sont déjà épinglés dans `requirements.txt`.

Pour SQL Server, le driver Python/ODBC exact sera validé dans l'environnement cible avant d'être figé dans les dépendances. SQLite reste le dialecte de développement et de test de SQL 4 / API 1.

## 2. Configuration par variables d'environnement

Le serveur n'utilise pas `app_config.json`. Sa configuration d'exploitation vient exclusivement de variables d'environnement.

| Variable | Requise | Défaut | Rôle |
|---|---:|---|---|
| `RESOURCEPLANNER_DATABASE_URL` | oui | — | URL SQLAlchemy de la base autoritaire |
| `RESOURCEPLANNER_HOST` | non | `127.0.0.1` | interface d'écoute Uvicorn |
| `RESOURCEPLANNER_PORT` | non | `8000` | port TCP, 1 à 65535 |
| `RESOURCEPLANNER_LOG_LEVEL` | non | `info` | `critical`, `error`, `warning`, `info`, `debug` ou `trace` |
| `RESOURCEPLANNER_ACTOR_NAME` | non | `api` | identité technique temporaire avant OIDC |

`RESOURCEPLANNER_DATABASE_URL` peut contenir des secrets. Ne jamais la committer dans Git ni la copier dans un fichier de configuration versionné.

### Exemple local SQLite

```bat
set RESOURCEPLANNER_DATABASE_URL=sqlite:///C:/Temp/resourceplanner_server.db
set RESOURCEPLANNER_HOST=127.0.0.1
set RESOURCEPLANNER_PORT=8000
```

### Exemple réseau interne

```bat
set RESOURCEPLANNER_HOST=0.0.0.0
set RESOURCEPLANNER_PORT=8000
```

`0.0.0.0` rend l'application accessible sur les interfaces réseau du serveur. Avant OIDC, cette configuration doit rester limitée à un environnement de test protégé par le réseau/pare-feu.

## 3. Migrations : étape explicite

Le serveur normal **n'exécute jamais Alembic automatiquement**. Les migrations sont une action d'exploitation séparée :

```bat
alembic upgrade head
```

`migrations/env.py` lit déjà `RESOURCEPLANNER_DATABASE_URL`.

Cette séparation évite qu'un simple redémarrage applicatif modifie le schéma de production de façon opportuniste.

## 4. Démarrer le serveur

Une fois la base configurée et migrée :

```bat
python -m app.server
```

Le point d'entrée charge les variables d'environnement, crée l'application FastAPI SQL et démarre Uvicorn sans mode reload.

Le runtime refuse de démarrer si `RESOURCEPLANNER_DATABASE_URL` est absente ou si le port / niveau de log est invalide.

## 5. Smoke tests

### Préflight automatisé en lecture seule

Avant même de laisser Uvicorn tourner en permanence, le dépôt fournit un préflight qui construit le même backend et vérifie la connexion ainsi que plusieurs routes sans modifier les données métier :

```bat
python tools\check_server_runtime.py
```

Le préflight vérifie :

- `/health`;
- la lecture des projets actifs;
- la lecture des ressources actives;
- la génération OpenAPI.

Sortie réussie typique :

```json
{"active_projects": 12, "active_resources": 20, "api": "v1", "database": "sqlite", "openapi_paths": 17, "status": "ok"}
```

Codes de sortie :

- `0` : configuration et lectures de base fonctionnelles;
- `2` : configuration serveur invalide ou `RESOURCEPLANNER_DATABASE_URL` absente;
- `3` : backend joignable partiellement mais smoke test en échec, par exemple schéma non migré;
- `4` : erreur d'infrastructure avant le smoke test, par exemple driver DBAPI/ODBC manquant.

Le rapport n'inclut jamais l'URL de connexion à la base. Pour une erreur technique inattendue, seul le type d'exception est affiché afin d'éviter qu'un mot de passe contenu dans l'URL SQL ne soit divulgué.

### Vérification manuelle après démarrage

Après `python -m app.server` :

```bat
curl http://127.0.0.1:8000/health
```

Réponse attendue pour SQLite :

```json
{"status":"ok","database":"sqlite","api":"v1"}
```

Puis vérifier au minimum :

```bat
curl http://127.0.0.1:8000/api/v1/projects
curl http://127.0.0.1:8000/api/v1/resources
curl "http://127.0.0.1:8000/api/v1/planning/snapshot?start=2026-08-24&end=2026-08-30"
```

La documentation OpenAPI est disponible à `/docs` et le schéma brut à `/openapi.json`.

## 6. Vérification avant branchement SQL Server

Lorsque l'environnement virtuel/serveur cible sera disponible :

1. identifier le driver ODBC SQL Server installé et sa version;
2. installer/valider le paquet Python correspondant (probablement `pyodbc`);
3. tester une URL SQLAlchemy SQL Server sans l'inscrire dans Git;
4. exécuter `alembic upgrade head` sur une base de développement dédiée;
5. exécuter `python tools\check_server_runtime.py`;
6. démarrer `python -m app.server`;
7. valider `/health`, les lectures et une transaction de commande avec rollback;
8. épingler le driver Python retenu dans les dépendances seulement après ce test;
9. définir ensuite le mode d'hébergement long terme (service Windows/process manager, compte de service, certificats TLS et reverse proxy si requis).

## 7. Limites volontaires de SQL 4 / API 1

Cette tranche ne met pas encore en place :

- Acumatica OIDC;
- autorisation par rôle;
- TLS/reverse proxy;
- service Windows ou autre superviseur de processus;
- frontend React;
- driver SQL Server final.

Ces éléments viennent après validation du runtime serveur de base afin de ne pas mélanger authentification, déploiement et migration de persistance dans la même tranche.

## 8. Relation avec le cutover Excel → SQL

Le basculement des données reste décrit dans [`SQL_CUTOVER_RUNBOOK.md`](SQL_CUTOVER_RUNBOOK.md).

Ordre recommandé le jour du cutover :

1. geler Excel;
2. migrer le schéma explicitement;
3. importer et réconcilier les données;
4. exécuter le préflight serveur en lecture seule;
5. démarrer le backend SQL;
6. exécuter les smoke tests manuels;
7. seulement ensuite déclarer SQL autoritaire.
