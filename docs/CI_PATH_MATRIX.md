# CI path-aware — matrice fichiers → validations

Le workflow principal `.github/workflows/syntax-check.yml` classe les fichiers modifiés avant de lancer les validations lourdes. Le classifieur est `tools/ci_change_classifier.py` et reste volontairement simple, déterministe et sans dépendance externe.

Le diff Git est calculé avec `--no-renames`. Un renommage est donc vu comme une suppression + un ajout, ce qui évite qu'un fichier déplacé depuis une zone applicative vers `docs/` soit classé à tort comme purement documentaire.

| Catégorie | Chemins principaux | server-isolation | Python shards | frontend-validation | docker-smoke |
| --- | --- | ---: | ---: | ---: | ---: |
| Documentation / processus seulement | `docs/**`, `AGENTS.md` | skip | skip | skip | skip |
| Backend / Python / tests / migrations | `app/**`, `tests/**`, `migrations/**`, `main.py`, `alembic.ini` | run | run | run | run |
| Frontend | `frontend/**` | skip | skip | run | run |
| Docker / déploiement / runtime partagé | Dockerfiles, Compose, scripts de lancement/installation, `deploy/**`, `.env.example`, `.dockerignore` | run | run | run | run |
| Dev Cockpit seulement | `dev-cockpit/**` | skip | skip | skip | skip |
| CI / dépendances / outillage | `.github/workflows/**`, `requirements*.txt`, `constraints*.txt`, `tools/**` | run | run | run | run |
| Chemin non reconnu | tout autre chemin qui déclenche le workflow | run | run | run | run |

## Règles fail-safe

- Un ensemble de changements vide est classé conservateur.
- Un chemin inconnu est classé conservateur.
- Une modification du workflow, des dépendances ou de l'outillage CI lance toutes les validations lourdes.
- Si le job de classification échoue, les quatre jobs lourds utilisent `always()` et se lancent quand même. Le job de classification reste en échec, donc la CI demeure rouge.
- Les noms existants des checks lourds restent inchangés; une validation non pertinente apparaît comme `skipped` plutôt que de disparaître du workflow.

## Cas représentatifs

| Diff PR | Classification | Validations lourdes attendues |
| --- | --- | --- |
| `docs/architecture/README.md` | documentation seulement | aucune |
| `AGENTS.md` + `docs/README.md` | documentation seulement | aucune |
| `frontend/src/App.tsx` | frontend | frontend-validation + docker-smoke |
| `app/server/api.py` | backend | les quatre validations |
| `migrations/versions/...` | backend | les quatre validations |
| `Dockerfile.backend` | runtime partagé | les quatre validations |
| `requirements-server.txt` | conservateur | les quatre validations |
| `.github/workflows/syntax-check.yml` | conservateur | les quatre validations |
| `tools/run_test_shard.py` | conservateur | les quatre validations |
| `dev-cockpit/frontend/src/App.tsx` | Dev Cockpit | aucune validation lourde du workflow principal; workflow `Dev Cockpit` dédié |
| `frontend/src/App.tsx` + `dev-cockpit/frontend/src/App.tsx` | frontend + Dev Cockpit | frontend-validation + docker-smoke dans CI, plus workflow `Dev Cockpit` |
| chemin futur non reconnu | conservateur | les quatre validations |

## Frontière Dev Cockpit

Le workflow principal déclare `dev-cockpit/**` dans son filtre `pull_request.paths` afin que le check requis **Classify changed files** existe aussi pour une PR strictement limitée au cockpit. Le classifieur reconnaît cette frontière et garde alors `backend=false`, `frontend=false`, `runtime=false` et `conservative=false` : les validations lourdes du runtime RessourcePlanner restent donc `skipped`, tandis que le workflow dédié `.github/workflows/dev-cockpit.yml` effectue la validation réelle du cockpit.

Les fichiers réellement partagés restent déclarés dans les deux workflows lorsque les deux surfaces doivent être validées, notamment `docker-compose.yml` et `.env.example`. Le workflow dédié lui-même reste couvert par le filtre global `.github/workflows/**` du workflow principal.

Pour une PR mixte RessourcePlanner + Dev Cockpit, un chemin applicatif déclenche la CI principale et le classifieur ignore la partie `dev-cockpit/**` afin de conserver uniquement les validations RessourcePlanner pertinentes; le chemin cockpit déclenche en parallèle le workflow dédié.


## Pilote trois shards Python — #370

Le pilote du 22 septembre 2026 a comparé la configuration actuelle à deux shards avec trois exécutions complètes à trois shards, sans modifier la couverture ni les poids historiques.

Baseline récente à deux shards (8 CI réussies) :
- chemin critique Python : médiane **114 s**; échantillons 104, 110, 111, 111, 117, 124, 125 et 266 s;
- consommation cumulée : médiane **219,5 runner-s**.

Pilote à trois shards :
- 1 127 tests exécutés à chaque run, répartis 372 / 405 / 350;
- poids prédits identiques à **30,175** par shard sur les trois runs;
- chemins critiques : **98 s**, **92 s**, **135 s**; médiane **98 s**;
- consommation cumulée : **255**, **240**, **267 runner-s**; médiane **255 runner-s**;
- installation des dépendances : **7 à 18 s** par shard selon le run;
- aucune exécution n'a atteint la cible indicative de **60–75 s**.

Le passage à trois shards réduit la médiane du chemin critique d'environ **14 %**, mais augmente la consommation médiane de runners d'environ **16 %** et présente une variabilité importante (un shard à 135 s malgré des poids historiques équilibrés). La configuration à **deux shards est donc conservée**. Les poids historiques n'ont pas été recalibrés, car leur distribution prédite restait parfaitement équilibrée et n'expliquait pas la variabilité observée.
