# Imports ERP Docker

Déposer ici l'export Excel des projets ERP à importer dans la base utilisée par Docker.

Les fichiers `.xlsx` et `.xlsm` sont ignorés par Git et ne doivent pas être commités.

Depuis la racine du dépôt :

```bash
docker compose run --rm import-projects /imports/Projets.xlsx
```

La commande ci-dessus fait une prévisualisation sans écrire dans la base.

Pour appliquer l'import :

```bash
docker compose run --rm import-projects /imports/Projets.xlsx --apply
```


## Catalogue de tâches

Prévisualiser :

```bash
docker compose run --rm import-tasks "/imports/Tâches de projet.xlsx"
```

Appliquer :

```bash
docker compose run --rm import-tasks "/imports/Tâches de projet.xlsx" --apply
```

Les fichiers CSV sont également acceptés. Voir `docs/ERP_TASK_CATALOG.md` pour le mapping.
