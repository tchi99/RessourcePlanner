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

`ODataProjectSource` est maintenant l'adaptateur projet utilisé par le runtime. Il lit le feed Atom/XML `/oDATA/RP_Projects`, construit un snapshot complet puis remet uniquement le contrat transport-neutre `ExternalProjectRecord` au `ProjectSyncService`.

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

Le mécanisme HTTP exact d'authentification du feed OData doit être confirmé avec l'instance réelle avant implémentation définitive.

## Validation réelle restant à faire

Les étapes locales 207A (adaptateur OData + parser + fixture contractuelle) sont couvertes hors connexion ERP. 207B doit maintenant :

1. configurer la base URL et le credential hors dépôt;
2. confirmer le mécanisme HTTP exact d'authentification;
3. effectuer un GET réel de la vue `RP_Projects`;
4. confirmer `ProjectId` comme identité stable sur plusieurs lectures;
5. confirmer le support réel du filtrage/pagination OData;
6. vérifier la fiabilité de `LastModifiedDateTime` pour l'incrémental;
7. lancer une synchronisation sur une base de développement;
8. relancer la synchronisation et confirmer l'idempotence;
9. valider quelques projets connus;
10. confirmer la règle métier de `BaseType`.

## Readiness locale

Les tests OData couvrent désormais le contrat Atom/XML et réutilisent les garanties déjà éprouvées — erreurs réseau/HTTP, snapshot complet, atomicité SQL, journalisation sûre, idempotence et absence de suppression implicite.

Voir [V2_ACUMATICA_READINESS.md](V2_ACUMATICA_READINESS.md) pour la distinction entre capacités réutilisables et travail OData restant.

Refs : #207 #232
