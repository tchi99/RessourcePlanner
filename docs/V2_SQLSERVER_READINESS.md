# Readiness SQL Server V2

Cette tranche réduit le risque du futur branchement SQL Server sans prétendre remplacer la validation réelle sur l'environnement cible. Les contrôles locaux/CI n'installent ni `pyodbc` ni un driver ODBC et ne contactent aucun SQL Server.

## Ce qui est validé sans SQL Server

La commande suivante exécute les contrôles locaux reproductibles :

```bash
python tools/check_sqlserver_readiness.py
```

Elle vérifie quatre choses :

1. toutes les migrations Alembic passent depuis une base SQLite vierge jusqu'à `head`;
2. toute la chaîne Alembic génère du DDL MSSQL en mode offline;
3. toutes les tables et tous les index SQLAlchemy compilent avec le dialecte SQL Server;
4. un ensemble de requêtes critiques V2 (`projects`, `resources`, `demands`, `segments`, `shifts`, historique, insert/update) compile avec le dialecte MSSQL.

Le CI exécute cette commande dans le job `server-isolation` avec seulement `requirements-server.txt`. Si le contrôle commence à dépendre de `pyodbc`, il échoue avant même qu'un vrai SQL Server soit impliqué.

## Hypothèses SQLite inventoriées

Les différences connues sont explicites et isolées :

- `create_sql_engine()` active `PRAGMA foreign_keys=ON` uniquement pour SQLite;
- Alembic active `render_as_batch=True` uniquement pour les migrations online SQLite;
- le schéma n'utilise pas de PK auto-incrémentée : les identifiants V2 sont des chaînes UUID générées par l'application;
- les booléens SQLAlchemy doivent compiler vers `BIT`/valeurs compatibles MSSQL; le DDL MSSQL offline est la garde de régression;
- les `DateTime(timezone=True)`, `Date`, `Time`, `Numeric`, `String(n)` et `Text` sont compilés par le dialecte MSSQL et validés statiquement;
- les valeurs par défaut serveur utilisent les expressions SQLAlchemy ou du SQL simple compatible, notamment `func.now()`, `true()`, `false()` et des littéraux;
- les upserts ERP actuels sont des séquences ORM `SELECT` puis création/mutation; ils ne dépendent pas de `INSERT ... ON CONFLICT` SQLite;
- l'index filtré `app_users.employee_external_id` possède explicitement un prédicat `sqlite_where` et un prédicat `mssql_where`;
- les noms de tables, colonnes, index et contraintes sont contrôlés sous la limite SQL Server de 128 caractères;
- les clés d'index/unicité basées sur des chaînes sont auditées avec un budget conservateur de 900 octets;
- les colonnes `Text` non bornées ne sont pas acceptées comme clés d'index par le contrôle readiness.

Les temps de performance SQLite de #252 ne sont toujours pas interprétés comme des performances SQL Server.

## Préflight runtime renforcé

`python tools/check_server_runtime.py` distingue maintenant les catégories suivantes :

| Statut | Signification |
| --- | --- |
| `configuration_error` | variable/configuration applicative invalide |
| `driver_error` | dialecte DBAPI ou driver ODBC absent |
| `connectivity_error` | driver chargé mais connexion/interrogation impossible |
| `migration_error` | `alembic_version` absente ou différente du `head` du dépôt |
| `readiness_error` | DB prête mais smoke HTTP/API non conforme |
| `technical_error` | erreur inattendue non classée |

Les messages ne réimpriment pas la chaîne de connexion ni les exceptions DBAPI susceptibles de contenir un hôte, un utilisateur ou un secret.

## Jour du branchement SQL Server (#162)

L'ordre recommandé est volontairement strict.

### 1. Valider le driver sur l'environnement cible

Installer d'abord le driver ODBC SQL Server approuvé sur le serveur cible. Ensuite seulement, installer le module Python DBAPI sans le figer dans les requirements génériques :

```bash
python -m pip install pyodbc
```

Puis valider que SQLAlchemy le charge avec la vraie configuration. Ne pas ajouter de version `pyodbc` dans `requirements-server.txt` avant que cette combinaison OS / Python / ODBC ait été validée.

### 2. Définir la connexion

Exemple de forme seulement — utiliser les paramètres et secrets du déploiement réel :

```text
RESOURCEPLANNER_DATABASE_URL=mssql+pyodbc://.../ResourcePlanner?driver=ODBC+Driver+18+for+SQL+Server
```

Ne pas stocker la chaîne réelle dans Git.

### 3. Rejouer les validations offline

```bash
python tools/check_sqlserver_readiness.py
```

### 4. Vérifier l'état Alembic avant mutation

```bash
python -m alembic current
python -m alembic heads
```

Sur une base vierge, `current` peut être vide avant la première migration.

### 5. Exécuter les migrations réelles

```bash
python -m alembic upgrade head
python -m alembic current
```

Le `current` final doit correspondre exactement au `head` du dépôt.

### 6. Lancer le préflight runtime complet

```bash
python tools/check_server_runtime.py
```

Il valide successivement configuration, driver, connectivité, migration et readiness HTTP.

### 7. Smoke SQL Server lecture seule

```bash
python tools/smoke_sqlserver_readonly.py
```

Ce smoke :

- exécute le préflight DB/Alembic;
- vérifie les tables V2 essentielles;
- exécute des lectures `TOP 1` sur projets, ressources, demandes, segments et quarts;
- n'effectue aucune modification métier.

### 8. Smoke transaction/rollback

À exécuter seulement après validation du smoke lecture seule :

```bash
python tools/smoke_sqlserver_transaction.py
```

Ce smoke crée une ligne projet sentinelle dans une transaction, confirme qu'elle est visible dans cette transaction, exécute explicitement `ROLLBACK`, puis ouvre une nouvelle connexion et confirme que la ligne n'existe plus. Le succès exige donc `business_rows_persisted=0`.

## Ce qui reste volontairement à #162

#253 ne remplace pas :

- l'installation et la compatibilité réelles du driver ODBC;
- TLS, DNS, pare-feu, authentification et permissions du SQL Server cible;
- l'exécution réelle des migrations sur SQL Server;
- les plans d'exécution, Query Store, verrous, concurrence et latence réseau;
- la validation de sauvegarde/restauration et du plan de retour arrière du déploiement.

Le but est qu'aucune refactorisation majeure de persistence ne soit encore nécessaire lorsque ces essais réels commencent.
