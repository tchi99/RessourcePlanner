# Développement Web V2 — React + FastAPI + SQLite

Le frontend React V2 peut être développé et validé sans attendre l'accès au SQL Server cible. Le navigateur ne connaît ni Excel ni SQL : il consomme uniquement FastAPI.

## Architecture locale

```text
React / Vite :5173
       │ proxy /api + /health
       ▼
FastAPI :8000
       │
       ▼
resourceplanner_server.db
```

Le remplacement ultérieur de SQLite par SQL Server ne doit nécessiter aucune modification métier du frontend.

## 1. Préparer le backend local

Depuis la racine du dépôt, `Lancer_Serveur.bat` est maintenant le chemin normal de développement :

```bat
Lancer_Serveur.bat
```

Si `RESOURCEPLANNER_DATABASE_URL` n'est pas déjà définie, le lanceur utilise automatiquement :

```text
sqlite:///./resourceplanner_server.db
```

Dans ce mode local SQLite, il applique aussi `alembic upgrade head` avant de démarrer FastAPI. Si une URL explicite est configurée plus tard pour SQL Server, elle est conservée et le lanceur n'exécute pas les migrations automatiquement.

Le serveur FastAPI doit répondre sur `http://127.0.0.1:8000/health`. La documentation interactive est disponible à `http://127.0.0.1:8000/docs`.

## 2. Charger un jeu de données de démonstration

Pour essayer l'interface React sans importer de données réelles, fermer le serveur puis lancer :

```bat
Charger_Donnees_Demo.bat
```

Le chargeur :

- utilise uniquement `resourceplanner_server.db` dans le dossier du projet;
- applique les migrations Alembic avant le chargement;
- refuse de fonctionner contre un moteur autre que SQLite;
- crée des projets, ressources, horaires standards, WorkPackages, demandes, périodes alternatives, besoins et quarts;
- replace les dates autour de la semaine courante à chaque exécution;
- remplace uniquement les données rattachées aux projets `DEMO-*`, afin d'éviter les doublons tout en laissant les autres données locales intactes.

Le jeu couvre notamment :

- plusieurs classes de ressources;
- quarts automatiques et manuels/verrouillés;
- confirmation ferme et tentative;
- Quick Shift hors horaire;
- demande `Soumise` visible comme charge potentielle;
- demande `Brouillon`;
- demande `À corriger`;
- période cumulative + deux dates alternatives exclusives dont une sélectionnée;
- plusieurs WorkPackages et chargés de projet.

Pour un test avec une copie de données V1 réelles, utiliser plutôt le CLI de cutover décrit dans `docs/SQL_CUTOVER_RUNBOOK.md`.

## 3. Démarrer React

Garder `Lancer_Serveur.bat` ouvert. Dans un deuxième terminal :

```bat
cd frontend
npm install
npm run dev
```

`npm install` est requis la première fois et après un changement de dépendances. Ouvrir ensuite `http://127.0.0.1:5173`.

Vite relaie automatiquement `/api` et `/health` vers `http://127.0.0.1:8000`. On évite ainsi d'ajouter une politique CORS uniquement pour le développement local.

## 4. API distante optionnelle

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

## 5. Build vérifié

```bat
cd frontend
npm install
npm run build
```

Le build exécute d'abord TypeScript en mode strict puis Vite. GitHub Actions exécute aussi ce build pour les PR touchant le frontend.

## 6. Portée actuelle

Le planning opérationnel Web V2 supporte maintenant :

- navigation hebdomadaire;
- ressources groupées par classe;
- quarts confirmés/tentatifs, verrouillés et hors horaire;
- charge ferme/potentielle et propositions de remplacement;
- demandes potentielles en attente;
- filtres projet, confirmation et recherche;
- édition d'un quart existant depuis sa carte;
- passage d'un quart automatique vers une décision manuelle/verrouillée lors d'une modification;
- override de confirmation du quart ou retour à l'héritage du segment;
- création d'un Quick Shift ad hoc directement sous un projet, sans WorkforceRequest fictif;
- chargement des projets et ressources actifs depuis les read models FastAPI;
- `Idempotency-Key` sur les Quick Shifts : un retry du même payload réutilise la même clé afin d'éviter les doublons;
- rechargement du snapshot après chaque mutation réussie.

L'espace Demandes React V2 supporte aussi la liste, le détail, la création/modification, les périodes cumulatives/alternatives et le workflow de soumission/approbation/correction/annulation. FastAPI reste la frontière métier autoritaire.

L'OIDC/RBAC, Acumatica, le SQL Server réel et l'hébergement de production restent hors de cette tranche de développement local.

Refs : #187, #189, #192, #95, #55, #162.
