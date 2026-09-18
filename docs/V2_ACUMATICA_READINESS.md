# V2 — Acumatica readiness locale

Cette tranche prépare la frontière Acumatica avant l'accès à l'instance réelle. Elle valide la résilience générique de l'adaptateur et des synchronisations sans prétendre valider le contrat métier réel.

## Ce qui est validé localement

La source projet actuelle reste une lecture seule du contract-based REST API :

```text
<base_url>/entity/<endpoint>/<version>/<entity>
```

Les tests locaux couvrent désormais :

- plusieurs pages avec `$top` + `$skip`;
- champs configurables;
- champs optionnels absents;
- projet incomplet sur un champ requis;
- JSON invalide;
- réponse JSON qui n'est pas une liste;
- ligne de liste qui n'est pas un objet;
- timeout HTTP;
- erreur réseau;
- HTTP 401;
- HTTP 403;
- HTTP 429;
- HTTP 5xx;
- échec sur une page ultérieure après une première page valide;
- synchronisation répétée idempotente;
- rollback transactionnel si une erreur survient après un premier upsert;
- conservation des projets/ressources absents d'un pull;
- aucune inactivation implicite lorsqu'un pull est incomplet;
- métriques `external` cohérentes sur succès et échec;
- journalisation technique sans token, corps HTTP ni payload projet.

## Sémantique d'un pull partiel

`AcumaticaProjectSource.list_projects()` construit le snapshot complet en mémoire avant de le remettre au service applicatif.

Conséquence importante :

```text
page 1 OK
   ↓
page 2 erreur
   ↓
exception
   ↓
ProjectSyncService ne reçoit aucun snapshot
   ↓
aucun upsert SQL
```

Une erreur après le début des upserts est également atomique : la route de synchronisation utilise une transaction SQL unique. Si une ligne ultérieure échoue, les écritures précédentes du même pull sont rollbackées.

L'absence d'un projet ou d'une ressource dans un pull ne signifie jamais suppression ou inactivation. Une inactivation doit être reçue explicitement dans un enregistrement valide.

## Classification technique des erreurs externes

Le code public reste `acumatica_project_read_failed` pour préserver le contrat API existant. Le contexte ajoute uniquement des informations techniques sûres :

| `failure_kind` | Cas | `retryable` |
| --- | --- | --- |
| `authentication` | HTTP 401 | false |
| `authorization` | HTTP 403 | false |
| `throttled` | HTTP 429 | true |
| `upstream_5xx` | HTTP 5xx | true |
| `timeout` | timeout réseau | true |
| `network` | erreur transport/réseau | true |
| `http_error` | autre erreur HTTP | false |
| `invalid_json` | corps non JSON | false |
| `invalid_payload` | forme JSON incompatible | false |

`retryable=true` est uniquement un diagnostic. Aucun retry automatique n'est ajouté avant de connaître le comportement réel de l'instance, les limites de taux et les règles du contrat #232.

Le contexte ne contient jamais :

- bearer token;
- secret client;
- corps de réponse Acumatica;
- URL de requête complète;
- nom/numéro de projet provenant du payload.

## Métriques de performance #22

Au niveau de la route de synchronisation, une lecture logique de la source compte comme un appel externe :

- succès : `external_call_count=1`, `external_item_count=N`;
- échec avant remise du snapshot : `external_call_count=1`, `external_item_count=0`;
- `external_seconds` couvre la durée de la lecture externe, succès ou exception.

Le compteur d'items représente donc les enregistrements effectivement remis au service de synchronisation, pas le nombre de lignes éventuellement lues avant une page qui échoue.

## Timeout runtime

Le timeout est configurable sans changer le contrat :

```text
RESOURCEPLANNER_ACUMATICA_TIMEOUT_SECONDS=30
```

Valeur par défaut : 30 secondes. La configuration accepte une valeur strictement positive jusqu'à 120 secondes.

## Hypothèses à confirmer/remplacer dans #232

Les éléments suivants ne sont **pas** considérés comme validés tant qu'ils n'ont pas été observés sur l'instance réelle :

- URL réelle de l'instance;
- endpoint et version exposés;
- nom réel de l'entité projet;
- présence et sens du champ REST `id`;
- noms des champs projet;
- enveloppe `{"value": ...}` des champs;
- support exact de `$select`, `$top` et `$skip`;
- sémantique des statuts projet;
- mapping du chargé de projet;
- mécanisme d'obtention/renouvellement du token;
- comportement et en-têtes de rate limiting;
- contrat Employee/User;
- identifiant employé réel;
- claims OIDC permettant éventuellement de relier identité et ressource;
- iframe/embedding réel.

Les valeurs par défaut actuelles sont des paramètres de développement configurables, pas une spécification de l'instance cible.

## Ce qui n'est volontairement pas implémenté ici

Cette tranche n'ajoute pas :

- `AcumaticaEmployeeSource` concret;
- mapping Employee/User hypothétique;
- nouvel identifiant employé supposé;
- budgets ou actuals Phase 2;
- retry automatique;
- push notifications;
- validation OIDC réelle;
- validation iframe réelle.

## Lorsque l'accès Acumatica sera disponible

L'ordre recommandé est :

1. exécuter #232 et relever le contrat réel depuis l'instance/endpoint;
2. renseigner ou adapter uniquement les paramètres/mappings observés;
3. exécuter les tests locaux de résilience;
4. lancer les smokes projet réels prévus par #207;
5. valider les fondations ressources/identité prévues par #223/#227 seulement avec les champs réellement observés;
6. traiter séparément OIDC et embedding réels.

Le but est que les surprises restantes soient liées au contrat réel de l'instance, et non à des problèmes génériques de pagination, réseau, atomicité ou observabilité.
