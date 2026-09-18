# Variables d'environnement du runtime V2

Ce document inventorie les variables du runtime Web. Il indique **quoi configurer**, pas les valeurs réelles. Les secrets ne doivent pas être committés dans Git, copiés dans les logs ou exposés par `/health` et `/ready`.

## Base de données et processus

| Variable | Usage | Requise |
| --- | --- | --- |
| `RESOURCEPLANNER_DATABASE_URL` | URL SQLAlchemy de la base | Oui pour `python -m app.server`; `Lancer_Web.bat` fournit SQLite local si absente |
| `RESOURCEPLANNER_HOST` | Adresse d'écoute | Non, défaut `127.0.0.1` |
| `RESOURCEPLANNER_PORT` | Port HTTP | Non, défaut `8000` |
| `RESOURCEPLANNER_LOG_LEVEL` | Niveau Uvicorn | Non, défaut `info` |
| `RESOURCEPLANNER_ACTOR_NAME` | Nom technique de l'acteur local | Non |
| `RESOURCEPLANNER_FRONTEND_DIST` | Build React servi par FastAPI | Défini automatiquement par `Lancer_Web.bat` |

## Authentification locale

| Variable | Usage |
| --- | --- |
| `RESOURCEPLANNER_AUTH_MODE` | `local` ou `oidc`; défaut `local` |
| `RESOURCEPLANNER_LOCAL_AUTH_NAME` | Nom affiché en mode local |
| `RESOURCEPLANNER_LOCAL_AUTH_EMAIL` | Courriel descriptif local |
| `RESOURCEPLANNER_LOCAL_AUTH_ROLES` | Rôles locaux |
| `RESOURCEPLANNER_ALLOW_LOCAL_AUTH_NETWORK` | Autorise explicitement le mode local hors loopback |

Le mode local refuse par défaut une écoute réseau. Ne pas utiliser l'override comme substitut à l'authentification réelle lors d'une exposition réseau.

## OIDC

Ces variables sont requises ou pertinentes lorsque `RESOURCEPLANNER_AUTH_MODE=oidc`.

| Variable | Usage | Secret |
| --- | --- | --- |
| `RESOURCEPLANNER_OIDC_DISCOVERY_URL` | Document de découverte OIDC | Non |
| `RESOURCEPLANNER_OIDC_CLIENT_ID` | Identifiant client | Non |
| `RESOURCEPLANNER_OIDC_CLIENT_SECRET` | Credential client lorsque requis | **Oui** |
| `RESOURCEPLANNER_OIDC_REDIRECT_URI` | Callback de l'application | Non |
| `RESOURCEPLANNER_OIDC_SCOPES` | Scopes, incluant obligatoirement `openid` | Non |
| `RESOURCEPLANNER_OIDC_COOKIE_NAME` | Nom du cookie de session | Non |
| `RESOURCEPLANNER_OIDC_SESSION_HOURS` | Durée de session | Non |
| `RESOURCEPLANNER_OIDC_SECURE_COOKIE` | Force le cookie Secure | Non |
| `RESOURCEPLANNER_OIDC_AUTO_PROVISION` | Active la politique d'auto-provisionnement prévue | Non |

Le préflight de démarrage vérifie la **configuration** OIDC, mais ne contacte pas le fournisseur d'identité. La validation réelle reste un smoke séparé.

## Acumatica

| Variable | Usage | Secret |
| --- | --- | --- |
| `RESOURCEPLANNER_ACUMATICA_BASE_URL` | URL de l'instance | Non |
| `RESOURCEPLANNER_ACUMATICA_ACCESS_TOKEN` | Bearer token runtime actuel | **Oui** |
| `RESOURCEPLANNER_ACUMATICA_ENDPOINT` | Endpoint contract-based REST | Non |
| `RESOURCEPLANNER_ACUMATICA_VERSION` | Version du contrat | Non |
| `RESOURCEPLANNER_ACUMATICA_PROJECT_ENTITY` | Entité projet | Non |
| `RESOURCEPLANNER_ACUMATICA_PROJECT_NUMBER_FIELD` | Champ numéro | Non |
| `RESOURCEPLANNER_ACUMATICA_PROJECT_NAME_FIELD` | Champ nom | Non |
| `RESOURCEPLANNER_ACUMATICA_PROJECT_CLIENT_FIELD` | Champ client | Non |
| `RESOURCEPLANNER_ACUMATICA_PROJECT_MANAGER_FIELD` | Champ chargé de projet | Non |
| `RESOURCEPLANNER_ACUMATICA_PROJECT_STATUS_FIELD` | Champ statut | Non |
| `RESOURCEPLANNER_ACUMATICA_PAGE_SIZE` | Taille des pages | Non |
| `RESOURCEPLANNER_ACUMATICA_TIMEOUT_SECONDS` | Timeout HTTP | Non |

L'absence d'Acumatica n'empêche pas les fonctions locales. Une configuration Acumatica **partielle** est par contre une erreur de configuration explicite au démarrage.

## Microsoft 365 / Graph

| Variable | Usage | Secret |
| --- | --- | --- |
| `RESOURCEPLANNER_M365_TENANT_ID` | Tenant | Non |
| `RESOURCEPLANNER_M365_CLIENT_ID` | Application cliente | Non |
| `RESOURCEPLANNER_M365_CLIENT_SECRET` | Credential applicatif | **Oui** |
| `RESOURCEPLANNER_M365_MAILBOX` | Boîte utilisée pour les brouillons | Donnée de configuration |
| `RESOURCEPLANNER_M365_GRAPH_BASE_URL` | Base Graph | Non |
| `RESOURCEPLANNER_M365_AUTHORITY_HOST` | Autorité OAuth | Non |
| `RESOURCEPLANNER_M365_TIMEOUT_SECONDS` | Timeout Graph | Non |

M365 reste optionnel pour la planification locale. Le runtime ne contacte pas Graph pendant `/health` ou `/ready`.

## Embedding / Teams

| Variable | Usage |
| --- | --- |
| `RESOURCEPLANNER_FRAME_ANCESTORS` | Origines explicitement autorisées par CSP `frame-ancestors` |
| `RESOURCEPLANNER_OIDC_COOKIE_SAMESITE` | `lax`, `strict` ou `none` |

Aucun wildcard n'est accepté pour `frame-ancestors`. Hors localhost, les origines doivent être HTTPS.

## Outils de vérification

`Verifier_Web.bat` utilise aussi :

| Variable | Usage |
| --- | --- |
| `RESOURCEPLANNER_BASE_URL` | Origine à tester; défaut `http://127.0.0.1:8000` |

Cette variable appartient au smoke d'exploitation, pas au serveur.
