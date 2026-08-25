# Audit local des imports de démarrage

Tant que GitHub Actions est indisponible, avant de reprendre un chantier de refactorisation majeur, exécuter localement :

```bash
python -m unittest tests.test_relative_import_integrity tests.test_v171_adapter_extraction tests.test_runtime_composition
```

Puis lancer l'application via `Lancer_Application.bat`.

Le test `test_relative_import_integrity` valide statiquement tous les imports relatifs sous `app/` et doit détecter les références vers des modules physiquement supprimés avant le démarrage réel.
