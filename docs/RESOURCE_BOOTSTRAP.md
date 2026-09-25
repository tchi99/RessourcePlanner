# Bootstrap temporaire des ressources — #447

Ce parcours initialise rapidement des ressources réalistes pour les tests utilisateur. Il est
temporaire et ne remplace pas la future source Employee/User OData suivie dans #256.

## Identité et propriété

L'identité d'import est uniquement `external_id`. Le nom et le courriel ne servent jamais de clé.
L'import possède `name`, `email`, `active`, `resource_class` et `sort_order` seulement
lorsque cette dernière valeur est fournie. Il ne supprime ni ne désactive une ressource absente,
et n'écrase jamais compétences, notes, coordonnateur ou autres propriétés locales.

## Format

CSV ou XLSX/XLSM sont acceptés. La feuille Excel par défaut est `Ressources`.

Colonnes requises : `external_id`, `name`, `active`, `resource_class`.

Colonnes optionnelles : `email`, `sort_order`, `working_days`, `start_time`, `end_time`.

```csv
external_id;name;email;active;resource_class;sort_order;working_days;start_time;end_time
EMP-TEST-001;Technicien Test 001;;true;Automatisation;10;Lun,Mar,Mer,Jeu,Ven;07:00;15:30
EMP-TEST-002;Technicien Test 002;;true;Installation;20;;;
```

Les trois colonnes d'horaire doivent être fournies ensemble. Si elles sont vides, aucun horaire
n'est inventé et le rapport compte la ressource dans **Sans horaire fourni**.

Lorsqu'un horaire est fourni et qu'aucun horaire standard actif n'existe, l'import crée une règle
canonique `Horaire standard`. Un replay identique la reconnaît comme inchangée. Si un horaire
standard actif différent existe déjà, il est conservé et le rapport l'indique; le bootstrap
n'écrase donc pas silencieusement une règle locale.

## Docker

Prévisualisation, sans écriture :

```bash
docker compose run --rm import-resources /imports/Ressources.csv
```

Application :

```bash
docker compose run --rm import-resources /imports/Ressources.csv --apply
```

Pour une feuille XLSX portant un autre nom, ajouter `--sheet-name Equipe`.

Le rapport distingue ressources créées, mises à jour, inchangées, lignes invalides, horaires
créés/identiques/conservés et ressources sans horaire. Une erreur ou collision annule la
transaction complète. Les vrais exports du PO restent hors Git.
