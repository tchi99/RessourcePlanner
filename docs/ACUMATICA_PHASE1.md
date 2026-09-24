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

Le code contient encore un adaptateur historique `AcumaticaProjectSource` qui cible le Contract-Based REST API JSON :

```text
<base_url>/entity/<endpoint>/<version>/<entity>
```

Cet adaptateur et ses variables de configuration associées ne représentent **plus la cible de production**.

Ils restent présents tant que la tranche OData n'a pas remplacé cette frontière technique.

Le service applicatif `ProjectSyncService`, le `ProjectSourcePort` et la persistance SQL doivent rester indépendants du protocole ERP afin que seule l'infrastructure Acumatica soit remplacée.

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

1. implémenter un adaptateur OData Atom/XML derrière `ProjectSourcePort`;
2. couvrir le parser avec l'échantillon anonymisé de `RP_Projects`;
3. configurer la base URL et le credential hors dépôt;
4. effectuer un GET réel de la vue `RP_Projects`;
5. confirmer `ProjectId` comme identité stable sur plusieurs lectures;
6. confirmer le support réel du filtrage/pagination OData;
7. vérifier la fiabilité de `LastModifiedDateTime` pour l'incrémental;
8. lancer une synchronisation sur une base de développement;
9. relancer la synchronisation et confirmer l'idempotence;
10. valider quelques projets connus avant utilisation en production.

## Readiness locale

Les tests historiques du client REST restent utiles comme preuve de plusieurs propriétés génériques — erreurs réseau, atomicité, journalisation sûre, idempotence — mais ne constituent plus une validation du protocole cible.

Voir [V2_ACUMATICA_READINESS.md](V2_ACUMATICA_READINESS.md) pour la distinction entre capacités réutilisables et travail OData restant.

Refs : #207 #232
