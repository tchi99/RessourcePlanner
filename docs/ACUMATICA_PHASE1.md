# Acumatica Phase 1 — synchronisation lecture seule des projets

Cette intégration garde une frontière stricte : **Acumatica → adaptateur Python → service applicatif → SQL → React**. Le navigateur ne communique jamais directement avec Acumatica.

## Contrat cible

La décision d'intégration a évolué : RessourcePlanner utilisera **OData** pour les synchronisations Acumatica et non le Contract-Based REST API.

Le contrat projet connu est documenté dans [ACUMATICA_ODATA_CONTRACT.md](ACUMATICA_ODATA_CONTRACT.md).

La vue cible est :

```text
/oDATA/RP_Projects
```

Le nom d'hôte réel et les credentials sont des données d'environnement et ne doivent pas être committés dans ce dépôt public.

Le feed projet est OData Atom/XML.

## Identité et mapping projet

Décisions confirmées :

- `ProjectId` est la clé unique du projet dans la base Acumatica et devient l'identité externe stable de RessourcePlanner;
- `ProjectCode` est le numéro de projet utilisé à l'interne;
- `DefaultBranchCode` représente la division;
- les chaînes OData paddées doivent être normalisées;
- les valeurs `m:null="true"` deviennent des valeurs nulles applicatives.

Le mapping complet des champs et divisions est centralisé dans [ACUMATICA_ODATA_CONTRACT.md](ACUMATICA_ODATA_CONTRACT.md).

## État du code actuel

`ODataProjectSource` est maintenant l'adaptateur projet utilisé par le runtime. Il lit le feed Atom/XML `/oDATA/RP_Projects` avec HTTP Basic, parcourt toutes les pages via `$orderby=ProjectId asc` + `$top/$skip`, construit un snapshot complet puis remet uniquement le contrat transport-neutre `ExternalProjectRecord` au `ProjectSyncService`. Une erreur sur une page intermédiaire empêche toute remise d'un snapshot partiel.

Le parser conserve aussi `CustomerID`, `StartDate`, `EndDate`, la division, `LastModifiedDateTime` et `BaseType` dans son record d'infrastructure. Le modèle `Project` actuel ne persiste pas encore ces champs supplémentaires; 207A ne l'élargit pas uniquement pour le transport.

L'ancien `AcumaticaProjectSource` REST/JSON reste importable pour compatibilité historique, mais le runtime projet ne le compose plus. `ProjectSyncService`, `ProjectSourcePort` et la persistance SQL restent inchangés et indépendants du protocole ERP.

## Routes RessourcePlanner

La frontière HTTP RessourcePlanner reste pertinente :

```text
GET /api/v1/integrations/acumatica
POST /api/v1/integrations/acumatica/projects/sync
```

Le changement REST → OData concerne la source ERP derrière ces routes, pas le contrat React → FastAPI.

## Sémantique de synchronisation

La synchronisation projet doit conserver les règles suivantes :

- résolution prioritaire par `erp_external_id = ProjectId`;
- rapprochement par numéro uniquement pour adopter explicitement un projet historique sans ID ERP;
- conflit explicite si un numéro local est déjà lié à un autre `ProjectId`;
- mise à jour des attributs ERP retenus sans supprimer l'historique local;
- aucune suppression locale basée sur l'absence d'un projet dans une réponse;
- une inactivation/annulation doit venir explicitement d'un enregistrement ERP;
- rejouer le même snapshot doit être idempotent.

## Authentification de développement

Pour les premiers smokes OData, un compte utilisateur nominatif peut être utilisé temporairement.

Aucun credential ne doit être :

- committé;
- stocké dans une image Docker;
- affiché dans les logs;
- renvoyé par une route de statut.

La cible d'exploitation demeure un **compte de service ERP dédié à RessourcePlanner** avec permissions minimales.

Le smoke réel du 2026-09-24 a confirmé HTTP Basic pour le feed OData de l'instance testée. Le runtime configure désormais le username et le mot de passe uniquement via l'environnement/secrets; le diagnostic public expose seulement le mode `basic`, jamais les valeurs.

## Validation réelle #207B

Le smoke manuel du 2026-09-24 a confirmé avant branchement RessourcePlanner :

- HTTP Basic;
- feed Atom/XML réel;
- `$filter` sur `ProjectId` et `ProjectCode`;
- `$orderby`;
- pagination `$top/$skip` avec ordre stable sur `ProjectId asc`, sans lien `rel="next"` observé;
- trois fenêtres successives de cinq projets distinctes;
- `LastModifiedDateTime` exposé comme `Edm.DateTime`, filtrable avec `datetime'...'` pour `eq/ge/gt` et ordonnable;
- décalage observé compatible avec UTC côté OData versus heure locale EDT côté UI;
- `BaseType` observés : `P` et `R`; `R` semble représenter des templates mais aucune règle de filtrage n'est encore décidée.

Le smoke RessourcePlanner réel a ensuite été exécuté avec succès sur une base de développement :

- endpoint d'intégration configuré : OK, sans fuite de credential;
- première synchronisation : `received=1286, created=1286, updated=0, unchanged=0`;
- plusieurs projets connus et leur mapping : vérifiés;
- accents, padding et valeurs nulles : vérifiés;
- seconde synchronisation inchangée : `received=1286, created=0, updated=0, unchanged=1286`;
- doublons : aucun;
- projets locaux préexistants : conservés.

Le parcours réel confirme donc le snapshot complet, l'idempotence et l'absence de suppression implicite.

Reste une décision métier séparée : `BaseType=R` semble représenter des templates sur l'instance observée, mais #207B ne l'exclut pas sans règle PO explicite. Le compte nominatif utilisé pour le smoke doit aussi être remplacé par un compte de service dédié avant exploitation durable.

## Readiness locale

Les tests OData couvrent désormais le contrat Atom/XML et réutilisent les garanties déjà éprouvées — erreurs réseau/HTTP, snapshot complet, atomicité SQL, journalisation sûre, idempotence et absence de suppression implicite.

Voir [V2_ACUMATICA_READINESS.md](V2_ACUMATICA_READINESS.md) pour la distinction entre capacités réutilisables et travail OData restant.

Refs : #207 #232
