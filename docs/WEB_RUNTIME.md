# Runtime Web autonome — React + FastAPI + SQL

Ce document décrit le mode d'exécution cible de RessourcePlanner avant le cutover SQL Server réel.

Le runtime normal ne lance ni NiceGUI, ni Excel, ni `main.py`. Un seul processus Uvicorn/FastAPI sert :

- l'interface React construite par Vite à `/`;
- les assets statiques à `/assets/...`;
- l'API à `/api/v1/...`;
- le liveness check à `/health`;
- le readiness check SQL/Alembic à `/ready`;
- OpenAPI à `/docs` et `/openapi.json`.

Le frontend utilise des URLs relatives. Il appelle donc FastAPI sur la même origine et aucun serveur Vite n'est requis en exploitation.

## 1. Installation Web

Prérequis sur une machine qui construit l'application :

- Python 3.11 ou 3.12;
- Node.js 22 avec npm.

Depuis la racine du dépôt :

```bat
Installer_Web.bat
```

L'installateur :

1. crée `.venv-web`;
2. installe uniquement `requirements-server.txt` avec les contraintes de release;
3. n'installe pas le profil `requirements-legacy.txt`;
4. installe les dépendances React;
5. exécute `npm run build`;
6. vérifie que `frontend\dist\index.html` existe.

`.venv-web` est volontairement distinct du `.venv` historique de la V1.

## 2. Démarrage local SQLite

Pour un poste local sans `RESOURCEPLANNER_DATABASE_URL` :

```bat
Lancer_Web.bat
```

Le lanceur utilise alors :

```text
sqlite:///./resourceplanner_server.db
```

Dans ce mode local seulement, il exécute `alembic upgrade head` avant le démarrage.

L'application est ensuite disponible par défaut à :

```text
http://127.0.0.1:8000/
```

Le build React est obligatoire. Si `frontend\dist` manque ou est incomplet, le lanceur refuse de démarrer et demande de relancer `Installer_Web.bat`.

## 3. Démarrage avec une base explicitement configurée

Définir la base avant le lancement :

```bat
set RESOURCEPLANNER_DATABASE_URL=<URL SQLAlchemy>
set RESOURCEPLANNER_HOST=127.0.0.1
set RESOURCEPLANNER_PORT=8000
Lancer_Web.bat
```

Quand `RESOURCEPLANNER_DATABASE_URL` est déjà définie, **le lanceur n'exécute aucune migration automatiquement**. La migration reste une étape d'exploitation explicite :

```bat
.venv-web\Scripts\python.exe -m alembic upgrade head
```

Cette règle doit rester en place pour SQL Server.

## 4. Configuration du frontend servi par FastAPI

`Lancer_Web.bat` définit automatiquement :

```text
RESOURCEPLANNER_FRONTEND_DIST=<racine du dépôt>\frontend\dist
```

`python -m app.server` conserve aussi son mode API seul : si cette variable est absente, `/` n'est pas servi et l'API fonctionne comme auparavant.

Si la variable est définie, le serveur exige un build React valide. Il ne retombe jamais silencieusement en mode API seul.

## 5. Smoke test du runtime complet

Après un build React :

```bat
.venv-web\Scripts\python.exe tools\check_web_runtime.py
```

Le smoke vérifie avec une base SQLite en mémoire :

- `/` retourne le `index.html` Vite;
- au moins un asset `/assets/...` est réellement servi;
- `/health` confirme la liveness sans toucher SQL;
- `/ready` confirme la connexion et la révision Alembic exacte;
- une route `/api/v1/...` inconnue retourne un vrai 404 JSON et n'est pas transformée en page React.

La CI exécute ce smoke après `npm run build`.

Après une installation réelle et un démarrage avec `Lancer_Web.bat`, exécuter `Verifier_Web.bat` dans une deuxième console. Ce smoke valide l'environnement `.venv-web`, l'absence de dépendances legacy, le frontend, `/health` et `/ready`.

## 6. Arrêt

En lancement interactif, utiliser `Ctrl+C` dans la console Uvicorn.

Cette tranche ne transforme pas encore RessourcePlanner en service Windows. Un superviseur de processus, un reverse proxy et TLS pourront être ajoutés avec la cible de déploiement réelle.

## 7. Mise à jour applicative

Séquence recommandée avant SQL Server réel :

1. arrêter `Lancer_Web.bat`;
2. mettre le dépôt à jour (`git pull` ou déployer une release validée);
3. relancer `Installer_Web.bat` pour mettre à jour les dépendances et reconstruire React;
4. si une base explicite est utilisée, exécuter les migrations Alembic séparément;
5. exécuter les préflights/smokes;
6. redémarrer `Lancer_Web.bat`.

Sur un serveur de production futur, préférer un artefact/release identifié plutôt qu'un `git pull` non contrôlé.

## 8. Rollback

Le rollback applicatif doit être explicite :

1. arrêter le runtime Web;
2. revenir au commit/release applicatif précédent validé;
3. reconstruire le frontend avec `Installer_Web.bat`;
4. vérifier la compatibilité du schéma SQL avec cette version;
5. restaurer une sauvegarde de base si le rollback applicatif n'est pas compatible avec les migrations déjà appliquées;
6. exécuter les smokes;
7. redémarrer.

Ne pas exécuter automatiquement `alembic downgrade` comme stratégie de rollback. La décision dépend de la migration et de la sauvegarde disponible.

## 9. Runtime V1 pendant la transition

`Lancer_Application.bat` est maintenant un alias de compatibilité qui avertit explicitement qu'il lance la V1 legacy.

Le point d'entrée historique est conservé sous :

```text
Lancer_Application_Legacy.bat
```

Il utilise `.venv`, `main.py`, NiceGUI et Excel. Il ne fait pas partie du runtime Web cible.

## 10. Limites avant le cutover réel

Le runtime Web autonome est prêt à être validé localement/SQLite, mais la déclaration SQL autoritaire reste bloquée par #162.

Avant exposition réseau réelle, il reste notamment à valider ou ajouter selon l'environnement :

- driver ODBC/`pyodbc` SQL Server;
- migrations et smoke sur la base SQL Server cible;
- Acumatica OIDC/RBAC;
- TLS/reverse proxy;
- service Windows ou superviseur;
- sauvegarde/restauration opérationnelle.

Le jour du cutover, suivre également `SQL_CUTOVER_RUNBOOK.md`.


## 11. Runbook d'exploitation

Les procédures détaillées de configuration, diagnostic, sauvegarde/restauration, remplacement SQLite → SQL Server, mise à jour et rollback sont centralisées dans :

- `V2_RUNTIME_OPERATIONS.md`;
- `ENVIRONMENT_VARIABLES.md`;
- `V2_SQLSERVER_READINESS.md`.


## 12. Docker / Synology

La voie Docker de #263 devient le chemin cible pour un déploiement Synology. Dans ce mode, le runtime n'est plus un unique processus qui sert aussi les assets React : le frontend est construit puis servi par Nginx, tandis que FastAPI reste un conteneur API séparé sur le réseau Docker.

Nginx conserve une origine unique pour le navigateur en proxifiant `/api/*`, `/health`, `/ready`, `/docs` et `/openapi.json` vers FastAPI.

Le chemin Windows `Installer_Web.bat` / `Lancer_Web.bat` reste disponible pendant la transition, mais il n'est plus requis sur un hôte Docker.

Voir `docs/DOCKER_SYNOLOGY.md` pour le démarrage local, les migrations contrôlées, la cible Container Manager, le versionnement des images et le rollback.
