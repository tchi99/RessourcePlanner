# Baseline de performance V2

Cette baseline mesure les lectures FastAPI V2 sur des jeux de données SQLite synthétiques et déterministes. Elle sert à repérer les régressions structurelles avant les essais sur SQL Server et Acumatica.

## Commande reproductible

```bash
python tools/benchmark_v2_api.py --iterations 5 --output /tmp/v2-performance-baseline.json
```

Pour reproduire exactement la garde CI :

```bash
python tools/benchmark_v2_api.py --iterations 3 --ci --output /tmp/v2-performance-baseline.json
```

Pour faire un vrai comparatif avant/après :

```bash
python tools/benchmark_v2_api.py --iterations 5 --output /tmp/v2-before.json
# appliquer la modification à mesurer
python tools/benchmark_v2_api.py --iterations 5 --compare /tmp/v2-before.json --output /tmp/v2-after.json
```

Le second rapport affiche les deltas p95, nombre maximal de requêtes SQL et répétition maximale d'une même empreinte SQL, pour chaque dataset et endpoint communs.

Il est aussi possible de limiter l'exécution à un volume :

```bash
python tools/benchmark_v2_api.py --dataset large --iterations 5
```

## Datasets

| Dataset | Projets | Ressources | Demandes | Segments | Quarts |
| --- | ---: | ---: | ---: | ---: | ---: |
| small | 8 | 16 | 32 | 16 | 48 |
| medium | 24 | 48 | 120 | 60 | 180 |
| large | 60 | 120 | 360 | 180 | 540 |

Les dates, statuts, confirmations, affectations et charges sont générés de façon déterministe. Une demande sur douze est `Soumise` afin d'exercer aussi la projection de charge potentielle.

## Parcours mesurés

La baseline couvre les lectures `projects`, `resources`, `demands`, `segments`, `shifts` et `planning/snapshot`. Pour chaque route, le rapport conserve uniquement des métriques techniques : p50/p95/p99, ventilation p95 auth/API/DB/compute/serialization/external, nombre de requêtes SQL, nombre de `SELECT`, répétition maximale d'une empreinte SQL et signal N+1. La ventilation des phases est visible dans le rapport texte et dans le JSON.

Aucun numéro de projet, identifiant de demande, nom de ressource, texte SQL ou paramètre SQL n'est écrit dans le rapport de performance.

## Budgets CI

Les budgets sont volontairement plus stricts sur les **comptages et invariants SQL** que sur le temps mur :

- les lectures simples doivent conserver un nombre de requêtes quasi constant quand le dataset grossit;
- un nouveau signal N+1 sur une lecture simple fait échouer la CI;
- `planning/snapshot` possède temporairement une exception explicite parce que `list_pending_loads` lit actuellement les demandes soumises individuellement; la croissance reste plafonnée pour détecter une aggravation;
- les limites p99 sont seulement des garde-fous contre une dégradation catastrophique du runner.

Cette exception ne signifie pas que le N+1 de `planning/snapshot` est acceptable à long terme; elle le rend mesurable et empêche qu'il empire silencieusement.

## Interprétation

**Les temps SQLite ne sont pas des objectifs de performance SQL Server.** Ils fournissent une baseline locale/CI comparative. Les seuils de production seront établis plus tard sur SQL Server avec le vrai réseau, les plans d'exécution, Query Store et les intégrations externes réelles.
