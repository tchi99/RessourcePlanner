# RessourcePlanner Dev Cockpit

Outil de développement local, isolé fonctionnellement de l'application métier RessourcePlanner. Il observe GitHub en lecture seule et génère un prompt court à copier dans un Dev ChatGPT. Il n'intègre aucune API IA/OpenAI et ne pilote aucun agent.

## Source de vérité

Le cockpit ne crée aucun roadmap parallèle. Il lit notamment :

- le roadmap maître GitHub configuré (`#55` par défaut);
- l'issue active et ses sous-tranches;
- les PR, branches, commits, Actions et jobs GitHub;
- `AGENTS.md` pour déterminer si l'enchaînement d'un même bloc est documenté;
- `docs/architecture/` pour signaler les ADR disponibles/applicables.

Une branche ou un commit n'est jamais considéré comme une preuve de `DONE`. Une PR fusionnée alors que l'issue/roadmap n'est pas explicitement à jour est signalée comme un décalage à régulariser.

## Architecture

```text
React + TypeScript + Vite
          ↓ same-origin /api
FastAPI Dev Cockpit
          ↓
GitHub REST API
```

Le build React est servi directement par FastAPI dans l'image finale. Aucune base SQL n'est utilisée.

## Docker Compose

Le service est disponible uniquement avec le profil `dev-tools` :

```bash
docker compose --profile dev-tools up -d --build
```

Adresses locales :

```text
RessourcePlanner  http://127.0.0.1:8080
Dev Cockpit       http://127.0.0.1:8081
```

Le service `dev-cockpit` est publié sur `127.0.0.1` seulement par défaut.

Le runtime métier normal reste inchangé :

```bash
docker compose up -d --build
```

ne démarre pas le cockpit.

## Configuration

Variables lues depuis le `.env` racine par Docker Compose :

```dotenv
DEV_COCKPIT_GITHUB_TOKEN=
DEV_COCKPIT_REPOSITORY=tchi99/RessourcePlanner
DEV_COCKPIT_ROADMAP_ISSUE=55
DEV_COCKPIT_STALLED_AFTER_MINUTES=30
DEV_COCKPIT_HTTP_PORT=8081
```

`DEV_COCKPIT_GITHUB_TOKEN` doit être un token GitHub local en lecture seule donnant accès au dépôt surveillé, aux Issues, PR et Actions. Le token :

- n'est jamais envoyé à React;
- n'est jamais retourné par l'API;
- n'est pas écrit dans les logs applicatifs;
- ne doit jamais être committé.

Sans token, `/api/dashboard` retourne une erreur de configuration explicite plutôt que d'essayer silencieusement un accès non authentifié.

## Détection STALLED

`STALLED` est dérivé lorsque :

```text
CI rouge
AND aucun workflow associé actuellement en cours
AND aucun nouveau commit depuis l'échec
AND dernier commit plus ancien que DEV_COCKPIT_STALLED_AFTER_MINUTES
```

L'UI affiche alors le temps écoulé depuis l'échec CI, l'absence de nouveau commit et l'absence de workflow actif.

## Développement local hors Docker

Backend :

```bash
python -m pip install -r dev-cockpit/backend/requirements.txt
PYTHONPATH=dev-cockpit/backend python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Frontend :

```bash
cd dev-cockpit/frontend
npm install
npm run dev
```

Vite écoute sur `127.0.0.1:5174` et relaie `/api` vers `127.0.0.1:8001`.

## Tests

```bash
PYTHONPATH=dev-cockpit/backend python -m unittest discover -s dev-cockpit/backend/tests -v
cd dev-cockpit/frontend && npm install --no-audit --no-fund && npm run build
```

Validation Compose :

```bash
docker compose config
docker compose --profile dev-tools config
```

Smoke ciblé :

```bash
docker compose --profile dev-tools up -d --build dev-cockpit
curl http://127.0.0.1:8081/api/health
curl http://127.0.0.1:8081/api/config
```
