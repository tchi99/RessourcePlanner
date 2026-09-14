# Runbook — FastAPI / SQL et runtime Web

Ce document décrit la frontière serveur canonique de RessourcePlanner. Le backend FastAPI ne dépend ni de NiceGUI, ni d'Excel. Le mode d'exploitation Web complet est détaillé dans [`WEB_RUNTIME.md`](WEB_RUNTIME.md).

## État actuel

Deux modes utilisent le même backend :

1. **API seule** : `python -m app.server`, sans frontend si `RESOURCEPLANNER_FRONTEND_DIST` est absente;
2. **Web autonome** : `Lancer_Web.bat`, qui sert le build React et l'API sur la même origine.

La validation finale SQL Server reste à faire dans #162. Tant que l'authentification Acumatica/OIDC n'est pas ajoutée, ne pas exposer le runtime sur un réseau non maîtrisé.

## 1. Dépendances serveur

Le profil canonique est :

```bat
python -m pip install -r requirements-server.txt -c constraints-release.txt
```

`requirements-server.txt` reste indépendant de NiceGUI, xlwings et openpyxl.

Pour une installation Web Windows reproductible, utiliser plutôt :

```bat
Installer_Web.bat
```

L'installateur crée `.venv-web` et construit `frontend\dist` avec Node.js 22.

## 2. Configuration par variables d'environnement

Le serveur n'utilise pas `app_config.json`. Sa configuration d'exploitation vient de variables d'environnement.

| Variable | Requise | Défaut | Rôle |
|---|---:|---|---|
| `RESOURCEPLANNER_DATABASE_URL` | oui pour `python -m app.server` | — | URL SQLAlchemy de la base autoritaire |
| `RESOURCEPLANNER_HOST` | non | `127.0.0.1` | interface d'écoute Uvicorn |
| `RESOURCEPLANNER_PORT` | non | `8000` | port TCP |
| `RESOURCEPLANNER_LOG_LEVEL` | non | `info` | niveau Uvicorn |
| `RESOURCEPLANNER_ACTOR_NAME` | non | `api` | identité technique temporaire avant OIDC |
| `RESOURCEPLANNER_FRONTEND_DIST` | non | — | build React à servir; s'il est défini, le build doit être valide |

Les variables Acumatica documentées dans `ACUMATICA_PHASE1.md` restent optionnelles tant que l'intégration n'est pas configurée.

`RESOURCEPLANNER_DATABASE_URL` et les tokens d'intégration peuvent contenir des secrets. Ne jamais les committer.

## 3. Migrations

Le serveur Python normal n'exécute jamais Alembic automatiquement :

```bat
python -m alembic upgrade head
```

`Lancer_Web.bat` et `Lancer_Serveur.bat` conservent une exception de commodité **uniquement pour leur fallback SQLite local**, lorsque `RESOURCEPLANNER_DATABASE_URL` n'était pas définie avant le lancement.

Avec une base explicitement configurée — notamment SQL Server — les migrations restent toujours explicites.

## 4. Démarrage API seul

Exemple :

```bat
set RESOURCEPLANNER_DATABASE_URL=sqlite:///C:/Temp/resourceplanner_server.db
python -m app.server
```

Endpoints principaux :

- `/health`;
- `/api/v1/...`;
- `/docs`;
- `/openapi.json`.

Dans ce mode, `/` retourne 404 si aucun build frontend n'est configuré.

## 5. Démarrage Web autonome

Après :

```bat
Installer_Web.bat
```

lancer :

```bat
Lancer_Web.bat
```

Le lanceur définit `RESOURCEPLANNER_FRONTEND_DIST` vers `frontend\dist`, vérifie le build, puis démarre le même `app.server`. L'interface est disponible par défaut à `http://127.0.0.1:8000/`.

Le runtime Web refuse de démarrer si le build React demandé est absent ou incomplet; il ne retombe pas silencieusement en API seule.

## 6. Préflights et smokes

### Backend configuré

```bat
python tools\check_server_runtime.py
```

Ce préflight vérifie notamment `/health`, les lectures de base et OpenAPI contre la base configurée.

### Isolation des dépendances serveur

```bat
python tools\check_server_dependency_isolation.py
```

La CI exécute ce test avec uniquement `requirements-server.txt` installé afin de garantir que FastAPI/SQL ne dépend pas du runtime V1.

### Runtime Web complet

Après `npm run build` :

```bat
python tools\check_web_runtime.py
```

Ce smoke vérifie le `index.html`, un asset Vite réel, `/health` et l'isolation du namespace `/api/v1`.

## 7. SQL Server — validation restante

Lorsque l'environnement cible sera disponible :

1. identifier le driver ODBC SQL Server et sa version;
2. installer/valider `pyodbc`;
3. tester une URL SQLAlchemy SQL Server sans l'inscrire dans Git;
4. exécuter `alembic upgrade head` sur une base de développement dédiée;
5. exécuter `python tools\check_server_runtime.py`;
6. démarrer le runtime Web avec `Lancer_Web.bat` ou la future supervision de service;
7. valider `/`, `/health`, les lectures et au moins une mutation métier;
8. épingler le driver retenu après validation.

## 8. Relation avec le cutover Excel → SQL

Le basculement des données reste décrit dans [`SQL_CUTOVER_RUNBOOK.md`](SQL_CUTOVER_RUNBOOK.md). Le runtime Web autonome ne déclare pas à lui seul SQL Server autoritaire.

Ordre de haut niveau le jour du cutover :

1. geler la V1/Excel;
2. migrer le schéma explicitement;
3. importer et réconcilier les données;
4. exécuter les préflights;
5. démarrer React + FastAPI sur SQL Server;
6. exécuter les smokes lecture + mutation;
7. seulement ensuite déclarer SQL autoritaire.

## 9. Runtime V1 legacy

`Lancer_Application.bat` est conservé comme alias de compatibilité explicite vers `Lancer_Application_Legacy.bat`.

La V1 utilise `.venv`, `main.py`, NiceGUI et Excel. Elle reste disponible uniquement pour la transition et n'est plus le mode cible.
