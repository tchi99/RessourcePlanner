# V2 — exploitation locale, diagnostic et rollback

Ce runbook prépare l'exploitation interne du runtime React + FastAPI avant le cutover SQL Server réel.

## 1. Modèle de probes

Le runtime distingue trois concepts.

### `GET /health` — liveness

`/health` confirme uniquement que le processus FastAPI répond :

```json
{"status": "ok", "api": "v1"}
```

Il ne contacte ni SQL, ni OIDC, ni Acumatica, ni Microsoft 365. Un problème de base ne doit donc pas transformer un processus vivant en faux « down ».

### `GET /ready` — readiness locale obligatoire

`/ready` vérifie :

- que la base est joignable;
- qu'elle est interrogeable;
- que `alembic_version` existe;
- que la révision correspond exactement à la tête Alembic du code déployé.

Si une de ces conditions échoue, le probe retourne HTTP 503 avec une raison technique sûre, par exemple `migration_required` ou `database_unavailable`. L'URL de connexion et les détails DBAPI ne sont jamais retournés.

### Dépendances externes

`/ready` expose uniquement des booléens de configuration pour OIDC, Acumatica et M365. Il **ne les ping pas**.

Acumatica et M365 sont optionnels pour les fonctions locales. Leur panne ne doit pas empêcher la consultation et la planification locales. OIDC est nécessaire à l'authentification lorsqu'il est choisi, mais son accès réseau est validé par un smoke d'authentification séparé plutôt que par le probe de readiness.

## 2. Installation sur un poste ou une VM propre

Prérequis de build/runtime local :

- Windows;
- Python 3.11 ou 3.12;
- Node.js 22 avec npm;
- accès aux dépôts de paquets pendant l'installation.

Exécuter :

```bat
Installer_Web.bat
```

L'installateur crée `.venv-web`, installe `requirements-server.txt` avec les contraintes de release et construit React. Il ne doit pas installer NiceGUI, xlwings ou openpyxl.

La CI `server-isolation` valide en parallèle que le serveur démarre avec le profil serveur seul, sans dépendances V1.

Après l'installation, le contrôle local de l'environnement est :

```bat
.venv-web\Scripts\python.exe tools\check_installed_web.py
```

Un statut `legacy_dependencies_present` indique que l'environnement Web n'est pas isolé comme attendu.

## 3. Démarrage

### SQLite local implicite

```bat
Lancer_Web.bat
```

Sans `RESOURCEPLANNER_DATABASE_URL`, le lanceur utilise `resourceplanner_server.db` et exécute `alembic upgrade head`.

### Base explicitement configurée

Lorsque `RESOURCEPLANNER_DATABASE_URL` existe, le lanceur **ne migre jamais automatiquement** la base. Les migrations doivent être une étape d'exploitation explicite :

```bat
.venv-web\Scripts\python.exe -m alembic upgrade head
```

Dans les deux modes, `Lancer_Web.bat` exécute ensuite :

```bat
.venv-web\Scripts\python.exe tools\check_server_runtime.py
```

Le serveur ne démarre que si le préflight est vert.

## 4. Diagnostics de démarrage

`check_server_runtime.py` distingue les familles suivantes :

- `configuration_error` : variable requise absente ou valeur invalide;
- `driver_error` : dialecte/DBAPI/ODBC indisponible;
- `connectivity_error` : driver chargé mais base non joignable/interrogeable;
- `migration_error` : schéma non initialisé ou révision Alembic incorrecte;
- `readiness_error` : runtime créé mais contrat de readiness non satisfait;
- `technical_error` : erreur non classée.

Les erreurs inattendues n'affichent pas le message brut d'une exception DBAPI afin d'éviter de divulguer une chaîne de connexion, un utilisateur, un host ou un secret.

En mode OIDC, le préflight n'essaie pas de simuler une session utilisateur et ne contacte pas l'IdP. Les lectures métier authentifiées sont alors marquées `skipped_oidc`.

## 5. Smoke après installation et démarrage

Lancer d'abord le serveur :

```bat
Lancer_Web.bat
```

Dans une deuxième console :

```bat
Verifier_Web.bat
```

Le vérificateur contrôle :

1. Python supporté;
2. dépendances serveur présentes;
3. absence de NiceGUI/xlwings/openpyxl dans `.venv-web`;
4. build React présent;
5. `/health` = vivant;
6. `/ready` = prêt;
7. `/` = frontend HTML servi.

Pour une autre origine :

```bat
set RESOURCEPLANNER_BASE_URL=https://adresse-interne
Verifier_Web.bat
```

Le smoke n'a besoin d'aucune identité utilisateur : il ne teste que les endpoints publics d'exploitation.

## 6. Logs et métriques techniques

Le journal de performance par défaut se trouve sous :

```text
%LOCALAPPDATA%\RessourcePlanner\logs\performance.jsonl
```

À défaut de `LOCALAPPDATA`, le runtime utilise le répertoire utilisateur `.resourceplanner/logs`.

Politique actuelle :

- fichier JSONL;
- rotation approximative à 1 000 000 octets;
- trois archives conservées : `.1`, `.2`, `.3`;
- `.1` est l'archive la plus récente;
- le lecteur de diagnostics traverse maintenant les archives et le fichier courant.

Le schéma contient uniquement des données techniques : route **template**, statuts, durées, compteurs SQL, fingerprints unidirectionnels, compteurs externes et type d'erreur. Les paramètres SQL, identifiants métier, noms de ressource, numéros de projet et payloads externes ne doivent jamais être écrits dans ce journal.

Lecture locale :

```bat
.venv-web\Scripts\python.exe tools\performance_report.py
```

## 7. Sauvegarde SQLite locale

Pour une sauvegarde de développement cohérente :

1. arrêter `Lancer_Web.bat`;
2. créer un répertoire de sauvegarde hors du fichier actif;
3. utiliser l'API de backup SQLite, même si une simple copie fonctionnerait normalement après arrêt;
4. vérifier l'intégrité de la sauvegarde;
5. conserver le commit/release applicatif associé.

Exemple :

```bat
mkdir backups
.venv-web\Scripts\python.exe -c "import sqlite3; s=sqlite3.connect(r'resourceplanner_server.db'); d=sqlite3.connect(r'backups\resourceplanner_server_backup.db'); s.backup(d); d.close(); s.close()"
.venv-web\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'backups\resourceplanner_server_backup.db'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
```

Le résultat attendu du second appel est `ok`.

## 8. Restauration SQLite locale

1. arrêter le runtime;
2. sauvegarder/renommer la base actuelle pour permettre un retour arrière;
3. vérifier `PRAGMA integrity_check` sur le fichier à restaurer;
4. remplacer `resourceplanner_server.db`;
5. vérifier la révision :

```bat
.venv-web\Scripts\python.exe -m alembic current
```

6. exécuter :

```bat
.venv-web\Scripts\python.exe tools\check_server_runtime.py
```

7. démarrer puis exécuter `Verifier_Web.bat`.

Ne jamais écraser une base active pendant qu'Uvicorn l'utilise.

## 9. Remplacement de SQLite par SQL Server

La bascule n'est pas une conversion implicite du fichier SQLite.

Procédure :

1. arrêter le runtime et conserver une sauvegarde SQLite;
2. valider le driver ODBC approuvé sur la cible;
3. installer `pyodbc` seulement après cette validation;
4. configurer `RESOURCEPLANNER_DATABASE_URL` vers SQL Server;
5. exécuter `tools\check_sqlserver_readiness.py`;
6. exécuter `alembic upgrade head` sur la nouvelle base;
7. exécuter `tools\check_server_runtime.py`;
8. exécuter les smokes SQL Server lecture seule et rollback;
9. migrer/importer les données métier selon la procédure de cutover, séparément du schéma;
10. démarrer l'application et exécuter `Verifier_Web.bat`.

Voir aussi `V2_SQLSERVER_READINESS.md`.

## 10. Mise à jour applicative

Séquence recommandée pour une release interne :

1. annoncer la fenêtre et empêcher les modifications;
2. arrêter le runtime;
3. sauvegarder la base;
4. relever le commit/release actuellement déployé;
5. déployer le nouveau commit/release;
6. relancer `Installer_Web.bat`;
7. pour une base explicitement configurée, exécuter `alembic upgrade head`;
8. exécuter `check_server_runtime.py`;
9. démarrer avec `Lancer_Web.bat`;
10. exécuter `Verifier_Web.bat`;
11. confirmer les parcours métier essentiels.

## 11. Rollback

Le rollback applicatif est volontairement séparé du rollback de données.

Si la nouvelle version échoue **avant toute migration destructive ou écriture incompatible** :

1. arrêter;
2. revenir au commit/release précédent validé;
3. reconstruire avec `Installer_Web.bat`;
4. exécuter le préflight;
5. démarrer et smokes.

Si la migration de schéma/données rend l'ancienne application incompatible :

1. arrêter;
2. restaurer la sauvegarde prise avant la release;
3. revenir au commit/release précédent;
4. vérifier Alembic;
5. préflight;
6. démarrer;
7. smoke.

Ne pas utiliser `alembic downgrade` automatiquement comme stratégie de rollback. Une migration doit être évaluée explicitement; la restauration d'une sauvegarde cohérente reste la voie sûre lorsque le schéma n'est pas rétrocompatible.

## 12. Checklist de mise en production interne

Avant ouverture aux utilisateurs :

- [ ] commit/release identifié et CI verte;
- [ ] `Installer_Web.bat` exécuté sans profil legacy;
- [ ] `check_installed_web.py` vert;
- [ ] variables d'environnement renseignées selon `ENVIRONMENT_VARIABLES.md`;
- [ ] secrets stockés hors Git;
- [ ] mode d'authentification choisi explicitement;
- [ ] exposition réseau locale interdite en auth locale sauf décision explicite;
- [ ] sauvegarde pré-déploiement créée et testée;
- [ ] `alembic current` correspond à `alembic heads`;
- [ ] `check_server_runtime.py` vert;
- [ ] `/health` répond 200;
- [ ] `/ready` répond 200;
- [ ] `Verifier_Web.bat` vert;
- [ ] comportement sans Acumatica/M365 confirmé pour les fonctions locales;
- [ ] logs techniques accessibles et rotation vérifiée;
- [ ] procédure de rollback connue avant la fenêtre de déploiement;
- [ ] pour SQL Server : smokes lecture seule + transaction rollback verts;
- [ ] pour OIDC réel : login/logout/callback validés séparément;
- [ ] pour embedding réel : CSP/cookies validés séparément;
- [ ] responsable de décision go/no-go identifié.

Le critère de sortie de cette tranche est que #208 n'ait plus à inventer les procédures d'exploitation; les valeurs réelles et validations des systèmes cibles restent à compléter.
