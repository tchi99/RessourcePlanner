# Développement Web V2 — React + FastAPI + SQLite

Cette tranche permet de développer le frontend React V2 sans attendre l'accès au SQL Server cible. Le navigateur ne connaît ni Excel ni SQL : il consomme uniquement FastAPI.

## Architecture locale

```text
React / Vite :5173
       │ proxy /api + /health
       ▼
FastAPI :8000
       │
       ▼
SQLite de développement
```

Le remplacement ultérieur de SQLite par SQL Server ne doit nécessiter aucune modification métier du frontend.

## 1. Préparer le backend local

Depuis la racine du dépôt :

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
set RESOURCEPLANNER_DATABASE_URL=sqlite:///C:/Temp/resourceplanner_web.db
alembic upgrade head
python -m app.server
```

Le serveur FastAPI doit répondre sur `http://127.0.0.1:8000/health`.

Pour obtenir des données réalistes, on peut aussi importer une copie du classeur V1 dans une base SQLite vide avec le CLI de cutover, en respectant `docs/SQL_CUTOVER_RUNBOOK.md`.

## 2. Démarrer React

Dans un deuxième terminal :

```bat
cd frontend
npm install
npm run dev
```

Ouvrir ensuite `http://127.0.0.1:5173`.

Vite relaie automatiquement `/api` et `/health` vers `http://127.0.0.1:8000`. On évite ainsi d'ajouter une politique CORS uniquement pour le développement local.

## 3. API distante optionnelle

En dehors du proxy Vite, le frontend accepte `VITE_API_BASE_URL`. Exemple :

```bat
set VITE_API_BASE_URL=https://resourceplanner-test.example.internal
npm run build
```

En production, la cible privilégiée reste un déploiement same-origin via reverse proxy :

```text
https://resourceplanner/
  ├─ /            → build React
  └─ /api/*       → FastAPI
```

## 4. Build vérifié

```bat
cd frontend
npm install
npm run build
```

Le build exécute d'abord TypeScript en mode strict puis Vite. GitHub Actions exécute aussi ce build pour les PR touchant le frontend.

## 5. Portée actuelle

La première tranche est volontairement read-only :

- shell/navigation V2;
- planning hebdomadaire;
- ressources groupées par classe;
- quarts confirmés/tentatifs, verrouillés et hors horaire;
- charge ferme/potentielle;
- propositions de remplacement;
- demandes potentielles en attente;
- filtres projet, confirmation et recherche.

Les commandes (édition de quart, Quick Shift, demandes et approbations) seront branchées ensuite sur les endpoints FastAPI idempotents existants.

Refs : #187, #55, #162.
