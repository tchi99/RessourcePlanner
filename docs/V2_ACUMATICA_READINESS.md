# V2 — Acumatica readiness locale

Cette tranche prépare la frontière Acumatica avant et pendant la validation contre l'instance réelle. Elle distingue désormais explicitement les comportements génériques déjà couverts du **contrat cible OData**.

## Décision de protocole

Les synchronisations métier Acumatica cibleront **OData**, pas le Contract-Based REST API.

Pour les projets, la vue connue est :

```text
/oDATA/RP_Projects
```

Le contrat fonctionnel et le mapping sont documentés dans [ACUMATICA_ODATA_CONTRACT.md](ACUMATICA_ODATA_CONTRACT.md).

## Garanties réutilisées et couvertes

Le runtime projet utilise maintenant `ODataProjectSource`. Les tests OData reprennent les garanties génériques déjà établies par l'ancien client REST :

- timeout HTTP;
- erreur réseau;
- HTTP 401;
- HTTP 403;
- HTTP 429;
- HTTP 5xx;
- échec avant remise du snapshot au service applicatif;
- synchronisation répétée idempotente;
- rollback transactionnel si une erreur survient pendant l'application du snapshot;
- conservation des projets/ressources absents d'un pull;
- aucune inactivation implicite lorsqu'un pull est incomplet;
- métriques externes cohérentes;
- journalisation technique sans credential ni payload métier.

Ces garanties sont conservées sans modifier `ProjectSyncService` ni la transaction SQL de synchronisation.

## Contrat OData projet connu

Le feed `RP_Projects` est Atom/XML.

Éléments confirmés pour l'implémentation :

- `ProjectId` est la clé unique Acumatica à utiliser comme identité externe stable;
- `ProjectCode` est le numéro de projet interne;
- `DefaultBranchCode` représente la division;
- les valeurs nulles utilisent `m:null="true"`;
- certaines chaînes utilisent `xml:space="preserve"` et peuvent être paddées;
- `LastModifiedDateTime` est disponible;
- `BaseType` est exposé mais sa règle de filtrage métier reste à confirmer.

Le parser est testé sur un fixture Atom/XML anonymisé fidèle au contrat, y compris namespaces, valeurs nulles, Unicode, `Edm.Int32`, `Edm.DateTime`, ordre variable des propriétés, divisions connues et `BaseType` P/R.

## Sémantique d'un pull partiel

La règle applicative reste :

```text
lecture externe complète
   ↓
si erreur avant snapshot complet
   ↓
exception
   ↓
ProjectSyncService ne reçoit aucun snapshot
   ↓
aucun upsert SQL
```

Une erreur pendant l'application SQL doit également rollbacker la transaction complète.

L'absence d'un projet ou d'une ressource dans un pull ne signifie jamais suppression ou inactivation. Une inactivation doit être reçue explicitement depuis la source.

## Classification technique des erreurs externes

Le contrat public doit continuer à distinguer au minimum :

| `failure_kind` | Cas | `retryable` |
| --- | --- | --- |
| `authentication` | authentification refusée | false |
| `authorization` | accès interdit | false |
| `throttled` | limitation de débit | true |
| `upstream_5xx` | erreur ERP | true |
| `timeout` | timeout réseau | true |
| `network` | erreur transport/réseau | true |
| `http_error` | autre erreur HTTP | false |
| `invalid_payload` | XML/OData incompatible | false |

Les catégories exactes pourront être raffinées pendant l'implémentation OData, mais aucun détail sensible ne doit être exposé.

Le contexte/log ne doit jamais contenir :

- mot de passe;
- cookie/session ERP;
- token;
- corps complet de réponse métier;
- URL contenant un credential;
- payload projet sensible.

## Performance et observabilité

Au niveau de la route de synchronisation, une lecture logique de la source reste comptée comme un appel externe.

Les métriques doivent représenter les enregistrements remis au service applicatif, pas les fragments éventuellement lus avant une erreur.

## Timeout runtime

Le timeout doit rester configurable.

La variable actuelle `RESOURCEPLANNER_ACUMATICA_TIMEOUT_SECONDS` peut être réutilisée si elle reste cohérente avec le nouvel adaptateur.

## Résultats réels #207B et hypothèses restantes

Confirmé sur l'instance réelle le 2026-09-24 :

- authentification HTTP Basic;
- `$filter` sur `ProjectId`, `ProjectCode` et `LastModifiedDateTime`;
- `$orderby`;
- pagination `$top/$skip` avec `ProjectId asc`;
- aucun lien Atom `rel="next"` observé;
- trois pages de cinq projets distinctes lors du smoke;
- `LastModifiedDateTime` en `Edm.DateTime`, avec `eq/ge/gt` et littéral `datetime'...'`;
- valeur temporelle observée cohérente avec UTC côté OData et heure locale côté UI au moment du smoke;
- `BaseType` observés : `P` et `R`.

Restent à confirmer ou décider :

- support et syntaxe de `$select`;
- volume total, limite maximale et taille de page optimale du feed;
- garantie temporelle exacte de `LastModifiedDateTime` avant toute synchro incrémentale;
- liste exhaustive des statuts;
- règle métier de `BaseType` (`R` semble correspondre aux templates, sans exclusion automatique);
- synchronisation réelle vers une base RessourcePlanner de développement et idempotence de ce parcours;
- feed OData Employee/User;
- clé stable des employés;
- relation entre identité OIDC et employé;
- embedding réel.

## Ce qui n'est volontairement pas considéré comme livré

- compte de service OData de production (HTTP Basic est validé temporairement avec un compte nominatif);
- `AcumaticaEmployeeSource` OData;
- synchro incrémentale fondée sur `LastModifiedDateTime`;
- retry automatique;
- push notifications;
- validation OIDC réelle;
- validation iframe réelle.

## Ordre recommandé

1. terminer 207B par la synchronisation réelle vers une base RessourcePlanner de développement et son replay idempotent;
2. confirmer la règle métier de `BaseType=R`;
3. conserver la synchro incrémentale hors scope jusqu'à définition d'un curseur robuste;
4. compléter #232 pour Employee/User et identité;
5. implémenter ensuite #256 avec la source OData réellement observée.

Le but est de conserver les garanties applicatives déjà acquises tout en remplaçant uniquement la frontière de transport devenue obsolète.
