# CI path-aware — matrice fichiers → validations

Le workflow principal `.github/workflows/syntax-check.yml` classe les fichiers modifiés avant de lancer les validations lourdes. Le classifieur est `tools/ci_change_classifier.py` et reste volontairement simple, déterministe et sans dépendance externe.

Le diff Git est calculé avec `--no-renames`. Un renommage est donc vu comme une suppression + un ajout, ce qui évite qu'un fichier déplacé depuis une zone applicative vers `docs/` soit classé à tort comme purement documentaire.

| Catégorie | Chemins principaux | server-isolation | Python shards | frontend-validation | docker-smoke |
| --- | --- | ---: | ---: | ---: | ---: |
| Documentation / processus seulement | `docs/**`, `AGENTS.md` | skip | skip | skip | skip |
| Backend / Python / tests / migrations | `app/**`, `tests/**`, `migrations/**`, `main.py`, `alembic.ini` | run | run | run | run |
| Frontend | `frontend/**` | skip | skip | run | run |
| Docker / déploiement / runtime partagé | Dockerfiles, Compose, scripts de lancement/installation, `deploy/**`, `.env.example`, `.dockerignore` | run | run | run | run |
| CI / dépendances / outillage | `.github/workflows/**`, `requirements*.txt`, `constraints*.txt`, `tools/**`, `dev-cockpit/**` | run | run | run | run |
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
| chemin futur non reconnu | conservateur | les quatre validations |

Le chantier #369 pourra affiner séparément le cas strictement `dev-cockpit/**`; #368 le garde volontairement conservateur afin de ne pas mélanger les deux optimisations.
