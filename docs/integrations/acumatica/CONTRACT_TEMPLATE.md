# Template de contrat OData Acumatica

> Copier ce fichier pour chaque nouveau feed validé par le PO/opérateur autorisé.
> Ne jamais y coller de credential, hostname privé inutile ni valeur métier réelle.

## Identification du feed

- **Nom logique :**
- **Chemin OData relatif :**
- **Format observé :** Atom/XML
- **Type d'entité observé :**
- **Fixture anonymisée associée :** `tests/fixtures/acumatica/<sample>.xml`
- **Date de validation réelle :**
- **Validé par :** rôle/fonction seulement, sans donnée personnelle si inutile

## Identité externe stable

- **Champ clé :**
- **Type OData :**
- **Pourquoi cette clé est stable :**
- **Événements qui ne doivent pas changer la clé :**
- **Cible RessourcePlanner :**

Ne jamais retenir un nom, une description ou une autre valeur d'affichage comme clé autoritaire sans preuve explicite que l'ERP la définit comme identité stable.

## Mapping des champs

| Champ OData | Type / nullabilité observés | Sémantique | Cible RessourcePlanner | Usage | Notes |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  | nécessaire / informatif / sensible-exclu |  |

Documenter uniquement les noms de champs et leur sémantique. Les exemples de valeurs doivent rester synthétiques dans la fixture.

## Normalisation

Décrire uniquement les transformations démontrées par le contrat, par exemple :

- trim de chaînes paddées;
- conversion d'un type OData;
- traitement explicite de `m:null="true"`;
- casse ou format d'un code lorsque cela est réellement observé.

Ne pas inventer de normalisation pour anticiper un feed non observé.

## Règles métier et admissibilité

- **Entités à synchroniser :**
- **Entités à exclure :**
- **Règle d'admissibilité déterministe :**
- **Comportement d'une entité explicitement inactive :**
- **Décisions qui restent au PO :**

Si la structure du feed ne permet pas de trancher une règle métier, laisser la décision ouverte.

## Capacités OData validées

Marquer seulement les capacités réellement testées par le PO/opérateur autorisé.

- [ ] `$filter`
  - champs/opérateurs nécessaires confirmés :
- [ ] `$orderby`
  - ordre stable utilisé :
- [ ] `$top/$skip`
  - taille de page testée :
- [ ] autre mécanisme de pagination :
- [ ] champ de dernière modification :
  - type :
  - opérateurs temporels confirmés :
- [ ] absence de doublons confirmée sur la requête retenue
- [ ] comportement des entités inactives observé
- [ ] autre capacité nécessaire :

Une capacité confirmée sur un autre feed ne vaut pas confirmation pour ce feed.

## Relation avec d'autres entités

Décrire uniquement les relations réellement exposées :

- **Entité liée :**
- **Champ source :**
- **Champ cible :**
- **Identité stable de la relation :**
- **Relation directe ou vue intermédiaire :**

Ne pas utiliser le nom ou le courriel comme jointure autoritaire.

## Fixture anonymisée

La fixture associée doit préserver :

- namespaces;
- noms exacts des propriétés;
- types OData;
- `m:null`;
- `xml:space="preserve"` si observé;
- ordre variable des propriétés lorsque pertinent;
- cas structurels nécessaires au contrat.

Elle ne doit contenir aucune donnée réelle de projet, client, employé, utilisateur, adresse, téléphone, courriel, hostname interne ou credential.

Validation locale recommandée :

```bash
python tools/inspect_odata_contract.py tests/fixtures/acumatica/<sample>.xml
```

Le rapport ne doit afficher que la structure du feed, jamais les valeurs des propriétés.

## Stratégie de synchronisation

- **Import initial :** complet / autre
- **Incrémental :** oui / non / à décider
- **Curseur incrémental :**
- **Réconciliation complète périodique :**
- **Absence d'une entité dans un pull :**
- **Inactivation explicite :**
- **Idempotence attendue :**

## Smoke réel après développement

Le smoke ERP final est exécuté par le PO/opérateur autorisé après CI locale.

Consigner uniquement :

- statut HTTP;
- format;
- nombre d'entrées;
- présence des champs attendus;
- capacités OData validées;
- métriques techniques utiles;
- écarts de contrat éventuels.

Ne jamais publier le payload réel.

## Questions ouvertes

1.
2.
3.

## Gate de développement

Le contrat est prêt pour DEV lorsque la fixture et les sections ci-dessus suffisent à coder sans inventer :

- le feed;
- la clé;
- les champs nécessaires;
- les règles métier;
- les capacités OData dont dépend l'adaptateur.
