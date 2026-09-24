# V2 — Acumatica readiness locale

Cette tranche prépare la frontière Acumatica avant et pendant la validation contre l'instance réelle. Elle distingue désormais explicitement les comportements génériques déjà couverts du **contrat cible OData**.

## Décision de protocole

Les synchronisations métier Acumatica cibleront **OData**, pas le Contract-Based REST API.

Pour les projets, la vue connue est :

```text
/oDATA/RP_Projects
```

Le contrat fonctionnel et le mapping sont documentés dans [ACUMATICA_ODATA_CONTRACT.md](ACUMATICA_ODATA_CONTRACT.md).

## Ce qui reste valide dans les tests historiques

La source projet actuelle est encore un client REST JSON historique. Ses tests ne valident plus le protocole cible, mais plusieurs propriétés restent directement pertinentes pour le futur adaptateur OData :

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

Ces garanties doivent être conservées lors du remplacement de l'adaptateur REST par l'adaptateur OData.

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

Le parser devra donc être testé sur Atom/XML et non sur une liste JSON.

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

## Hypothèses encore à confirmer dans #232 / #207

Même avec le contrat `RP_Projects` connu, il reste à confirmer sur l'instance réelle :

- mécanisme HTTP exact d'authentification OData;
- support et syntaxe de `$select`;
- support de `$filter`;
- support de `$orderby`;
- pagination réelle et éventuels liens `next`;
- stabilité et ordre de `LastModifiedDateTime`;
- liste exhaustive des statuts;
- règle métier de `BaseType`;
- volume total et limites pratiques du feed;
- feed OData Employee/User;
- clé stable des employés;
- relation entre identité OIDC et employé;
- embedding réel.

## Ce qui n'est volontairement pas considéré comme livré

- adaptateur OData projet concret;
- parser Atom/XML de production;
- authentification de service OData;
- `AcumaticaEmployeeSource` OData;
- synchro incrémentale fondée sur `LastModifiedDateTime`;
- retry automatique;
- push notifications;
- validation OIDC réelle;
- validation iframe réelle.

## Ordre recommandé

1. utiliser le contrat documenté dans `ACUMATICA_ODATA_CONTRACT.md`;
2. implémenter l'adaptateur OData projet derrière `ProjectSourcePort`;
3. tester avec le sample anonymisé;
4. exécuter #207 contre le vrai feed;
5. confirmer filtrage/pagination/incrémental;
6. compléter #232 pour Employee/User et identité;
7. implémenter ensuite #256 avec la source OData réellement observée.

Le but est de conserver les garanties applicatives déjà acquises tout en remplaçant uniquement la frontière de transport devenue obsolète.
