# Architecture actuelle des demandes V2

> Ce document décrit l'état **implémenté sur `main` après #329**.  
> Le roadmap maître reste l'issue #55. Les décisions durables sont détaillées dans ADR-001 à ADR-004.

## 1. Chaîne métier canonique

Pour une demande de main-d'œuvre issue du workflow normal :

```text
Project
└── WorkforceRequest
    └── RequestLine
        ├── WorkforceRequestPeriod
        └── ResourceRequirement
            └── Shift
```

Responsabilités :

- `WorkforceRequest` est l'entête de workflow : numéro de demande, projet, demandeur canonique, priorité, description, statut et version d'agrégat;
- `RequestLine` est le besoin demandé planifiable : classe, compétences, dates, effort, confirmation, tâche ERP, WorkPackage, ressource proposée et description;
- `WorkforceRequestPeriod` représente les fenêtres détaillées d'une ligne, y compris les groupes alternatifs;
- `ResourceRequirement` est le besoin/budget opérationnel matérialisé;
- `Shift` est l'affectation réelle d'heures à une ressource et une date.

Le schéma conserve encore certains champs historiques sur `WorkforceRequest` pour compatibilité. Pour les nouvelles demandes multi-lignes, les propriétés propres au besoin planifiable appartiennent à `RequestLine`.

Le chemin ad hoc reste distinct :

```text
Project
└── ResourceRequirement [QUICK_SHIFT / AD_HOC]
    └── Shift
```

Un Quick Shift ne crée pas de fausse `WorkforceRequest`.

## 2. WorkPackage

`WorkPackage` est une référence de contexte/portée et non un parent obligatoire de toute demande.

Une `RequestLine` peut référencer son WorkPackage. Le schéma conserve aussi un champ historique au niveau de `WorkforceRequest`; il ne faut pas en déduire que toutes les lignes d'une demande multi-lignes partagent nécessairement le même WorkPackage.

Cette distinction est importante pour les évolutions futures : Planning, Delivery et Verification pourront se rejoindre autour du WorkPackage sans modifier la hiérarchie canonique des demandes.

## 3. Périodes et alternatives

ADR-002 fixe la propriété métier des périodes au niveau de `RequestLine`.

Identités importantes :

```text
RequestLine                → RequestLine.id
période logique            → (request_line_id, period_key)
version physique période   → WorkforceRequestPeriod.id
groupe alternatif          → (request_line_id, group_key)
```

Les périodes cumulatives s'additionnent. Les options d'un même groupe alternatif sont exclusives.

Les routes et nouvelles surfaces React doivent travailler par ligne. Les anciennes associations à la demande peuvent rester présentes pour compatibilité/navigation, mais ne doivent pas redevenir la frontière métier principale.

## 4. Besoin, cible automatique et affectation réelle

ADR-001 sépare deux concepts qui ne doivent plus être confondus :

- `ResourceRequirement.assigned_resource_id` : cible de génération automatique du reliquat;
- `Shift.resource_id` : ressource réellement affectée au quart.

Un même `ResourceRequirement` peut donc avoir des quarts sur plusieurs ressources.

Créer, modifier ou déplacer un quart ne doit pas changer implicitement la cible automatique.

## 5. Demandeur, acteur et contacts métier

Depuis #328, le demandeur possède une identité canonique stable distincte :

```text
acteur authentifié
      ≠
demandeur métier
      ≠
Resource planifiable
      ≠
responsable opérationnel / coordonnateur
```

Règles principales :

- un `PROJECT_MANAGER` ne peut pas usurper un autre demandeur par appel API;
- un `COORDINATOR` peut déléguer explicitement vers un demandeur admissible;
- l'acteur réel de la mutation reste distinct dans l'audit;
- nom et courriel sont des valeurs d'affichage/snapshot, pas des clés autoritaires;
- les données historiques ambiguës restent lisibles sans inventer de lien stable.

Les contacts métier de #289 restent un autre concept : `BusinessContact` n'est pas `AppUser`.

## 6. Candidat, autorisation approuvée et plan actif

ADR-003 et ADR-004 imposent trois états distincts :

```text
demande candidate
      ↓ approbation
RequestApprovalRevision immuable
      ↓ matérialisation / choix opérationnels
plan actif
```

Une modification candidate hors enveloppe n'altère pas le plan actif avant approbation.

La révision approuvée est la preuve d'autorisation. Les `ResourceRequirement` et `Shift` sont l'état opérationnel résultant, pas une reconstruction suffisante de ce qui avait été approuvé.

Les choix opérationnels autorisés, comme certaines confirmations ou sélections d'alternatives déjà approuvées, peuvent évoluer sans transformer silencieusement la demande candidate en nouvelle autorisation.

## 7. Projection de détail unifiée (#329)

Le backend expose maintenant :

```text
GET /api/v1/demands/{number}/detail
```

Cette projection compose les services/read models existants; elle ne crée pas de nouvel agrégat persistant.

Elle regroupe notamment :

- entête et version;
- lignes actives;
- périodes par ligne;
- groupes alternatifs et sélection;
- contacts effectifs;
- résumé du plan matérialisé;
- cible automatique et ressources réellement mobilisées;
- workflow et actions disponibles;
- état d'approbation;
- politique d'édition et versions attendues;
- diagnostics.

La résolution de contacts par ligne est chargée en lot afin d'éviter un N+1 systématique.

Le delta détaillé et l'historique complet peuvent rester chargés séparément lorsque nécessaire.

## 8. Frontend : tranche active #330

#330 doit remplacer la fragmentation `Demandes / Workflow / Périodes` par un détail réutilisable.

Architecture indicative :

```text
DemandsWorkspace
├── DemandList
└── DemandDetail
    ├── DemandHeaderForm
    ├── DemandLinesEditor
    │   └── DemandLinePeriodsEditor
    ├── DemandAdvancedOptions
    ├── DemandPlanDelta
    ├── DemandWorkflowActions
    └── DemandHistory
```

Contraintes :

- utiliser la projection #329 comme contexte principal;
- actions et permissions viennent du backend;
- périodes éditées par `RequestLine`;
- aucune matrice rôle → permissions dupliquée dans React;
- même détail ouvrable depuis Demandes et Planning;
- préserver les versions attendues et la gestion de concurrence;
- protéger les modifications non sauvegardées;
- delta et historique restent accessibles dans le même espace fonctionnel.

#330 est une consolidation frontend. Une nouvelle persistance, un nouveau cache/snapshot autoritaire ou une nouvelle frontière frontend/backend nécessiterait une revue architecturale avant d'élargir la tranche.

## 9. Séquence produit

État au 2026-09-22 :

```text
#13  ✅ enveloppe approuvée commune
#328 ✅ identité canonique du demandeur
#329 ✅ projection backend de détail
#330 🟡 détail React unifié
  ↓
#332 partage / duplication atomiques
  ↓
#333 extension de fenêtre + dialogue DnD
  ↓
#291 actifs réservables
  ↓
#292 qualifications d'actifs
  ↓
#276 routage d'approbation par tâche
  ↓
#278 dashboard Coordonnateur
```

L'ordre autoritaire reste #55.

## 10. Références

- #55 — roadmap maître;
- #13 — enveloppe approuvée commune;
- #288 — lignes multiples;
- #289 — contacts métier;
- #327 — actions/workflow backend autoritaires;
- #328 — identité canonique du demandeur;
- #329 — projection de détail unifiée;
- #330 — détail React unifié;
- #331 — cible automatique vs ressources réelles;
- ADR-001 — cible du besoin vs affectation réelle;
- ADR-002 — périodes par ligne;
- ADR-003 — autorisation approuvée immuable;
- ADR-004 — candidat / autorisation / plan actif.
