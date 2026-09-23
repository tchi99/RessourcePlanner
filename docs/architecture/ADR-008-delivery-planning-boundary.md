# ADR-008 — Delivery distinct du Planning et projection de capacité WorkPackage

Status: Accepted  
Date: 2026-09-23

## Context

RessourcePlanner planifie déjà les besoins, les ressources humaines, les actifs et leurs affectations réelles.

L'issue #362 ajoute un domaine Delivery pour représenter le travail technique à réaliser sous un `WorkPackage` : Epics, Stories, Kanban, progression et forecast.

L'analyse d'impact effectuée sur `main@4fb40665a0789830485cde6cfe7a25c77a82f473` confirme qu'une extension additive du monolithe suffit. Le moteur Planning n'a pas besoin d'être refondu.

Plusieurs ambiguïtés doivent cependant être évitées :

- les heures actuelles du WorkPackage sont modifiables et ne constituent pas encore une enveloppe budgétaire approuvée/versionnée;
- le restant Planning représente de la capacité encore à affecter, pas du travail technique restant;
- un `Shift` prouve une réservation de capacité, pas du travail réellement consommé;
- une modification candidate d'une demande ne doit pas déplacer silencieusement la capacité affichée dans Delivery;
- les techniciens doivent pouvoir travailler sur des Stories sans recevoir des droits de mutation Planning;
- les mutations du board ont une concurrence propre et ne doivent pas utiliser `planning_version` lorsqu'elles ne modifient pas Planning.

## Decision

### 1. Delivery est un domaine distinct de Planning dans le même monolithe

RessourcePlanner conserve un monolithe modulaire.

Le `WorkPackage` est le point de jonction entre Planning et Delivery :

```text
Project
└── WorkPackage
    ├── Planning
    │   ├── ResourceRequirement
    │   ├── Shift
    │   ├── AssetRequirement
    │   └── AssetAllocation
    │
    └── DeliveryPlan
        └── DeliveryItem
            ├── EPIC
            └── STORY
```

Planning reste autoritaire pour la capacité réservée.  
Delivery reste autoritaire pour le découpage technique, les estimations, le travail restant, les statuts et le forecast.

Une Story ne crée, ne déplace ni ne supprime automatiquement un `Shift`.

### 2. Un DeliveryPlan par WorkPackage

Le MVP utilise un `DeliveryPlan` logique par WorkPackage.

Le plan possède une identité stable, un cycle de vie propre, un `lead_user_id` facultatif et une version de concurrence Delivery.

Cycle de vie initial :

```text
DRAFT → ACTIVE → ARCHIVED
```

Un seul plan non archivé est autorisé par WorkPackage dans le MVP.

### 3. DeliveryItem hiérarchique avec identités stables

Le MVP utilise un modèle hiérarchique `DeliveryItem` avec au minimum :

- `EPIC`;
- `STORY`.

Les IDs sont stables et utilisés dans les commandes, projections, liens Verification et intégrations futures.

Règles initiales :

- un EPIC peut contenir des STORY;
- une STORY ne contient pas d'enfant;
- pas de hiérarchie arbitraire;
- une Story ayant déjà participé au suivi est annulée/archivée plutôt que supprimée silencieusement.

Statuts Story initiaux :

```text
BACKLOG
TODO
IN_PROGRESS
BLOCKED
DONE
CANCELLED
```

### 4. Les responsables Delivery sont des AppUser

Les responsables, assignees et Team Lead sont liés à `AppUser`.

Le domaine Delivery ne doit pas utiliser le nom d'affichage comme identité stable et ne doit pas exiger qu'une personne soit modélisée comme `ResourceProfile` pour posséder une Story.

Cela permet de conserver la distinction entre identité applicative, ressource planifiable et droits métier.

### 5. Les heures actuelles du WorkPackage sont une référence, pas un budget approuvé

Les heures actuellement présentes sur le WorkPackage sont une **référence de planification**.

Elles ne doivent pas être présentées comme un budget autorisé tant qu'aucune source canonique/versionnée n'existe pour cette notion.

Delivery doit distinguer :

1. référence WorkPackage;
2. capacité réservée Planning;
3. estimation technique Delivery;
4. travail restant Delivery;
5. éventuel budget autorisé futur provenant d'une source canonique, notamment Acumatica.

Une réestimation Delivery ne modifie jamais automatiquement la référence WorkPackage ni un futur budget autorisé.

### 6. Le restant Planning n'est pas le travail restant Delivery

Le restant Planning représente les heures de besoin encore à affecter selon les règles Planning.

Le travail restant Delivery est porté par les Stories.

Ces valeurs ne doivent pas être combinées ou renommées comme si elles représentaient le même concept.

### 7. Un Shift n'est pas un actual

Un `Shift` est une réservation/affectation de capacité.

Il ne prouve pas que les heures ont réellement été travaillées.

Tant qu'aucune source d'actuals/feuilles de temps autoritaire n'est intégrée :

- Delivery peut comparer capacité réservée et travail restant;
- le système peut produire un forecast de couverture;
- il ne doit pas calculer une consommation réelle à partir des Shift.

### 8. Progression objective et forecast séparé

Le MVP n'utilise pas de pourcentage manuel par Story.

Une Story contribue comme terminée uniquement lorsque son statut est `DONE`.

La progression consolidée est pondérée par une **estimation de référence stable** :

```text
progression =
somme(estimation_reference des Stories DONE)
/
somme(estimation_reference des Stories incluses)
```

Une réestimation ultérieure ne doit pas réécrire silencieusement l'historique de progression.

Les Stories non estimées doivent être visibles dans la couverture de l'indicateur. Si aucune estimation de référence exploitable n'existe, le système ne doit pas inventer un pourcentage trompeur.

Le forecast reste séparé. Il utilise le travail restant courant des Stories non terminées.

### 9. La capacité Delivery provient du plan actif/approuvé

Delivery consomme une projection backend read-only de la capacité Planning associée au WorkPackage du plan **actif/approuvé**.

Une modification candidate d'une demande ne doit pas déplacer silencieusement cette capacité avant approbation/activation.

La projection doit exposer les références/version nécessaires pour expliquer sa provenance et sa fraîcheur.

### 10. Concurrence Delivery indépendante

Les mutations purement Delivery utilisent une version persistante propre au board, par exemple `delivery_version`.

Elles ne participent pas à `planning_version` lorsqu'elles ne modifient pas Planning.

Si une fonctionnalité future doit réellement modifier Planning, elle doit passer par les commandes et garanties existantes de Planning plutôt que contourner ADR-006.

### 11. Permissions Delivery indépendantes de Planning

Les droits Delivery sont distincts des permissions Planning.

Un technicien peut recevoir le droit de mettre à jour ses Stories sans recevoir `manage_planning`.

La politique backend combine permission Delivery et contexte :

- chargé de projet/administrateur : cycle de vie du plan, lead, grandes priorités/échéances;
- Team Lead du plan : découpage, ordre, assignation, estimation et gestion du board;
- technicien : statut, travail restant et informations de blocage sur ses Stories autorisées.

React peut masquer ou présenter des actions, mais ne constitue pas la barrière d'autorisation.

### 12. Sprints optionnels

Le Kanban continu doit fonctionner sans sprint.

Les sprints sont un regroupement facultatif. #362 n'introduit pas un moteur Scrum complet.

### 13. Frontière avec Verification

#362 fournit des IDs Story stables et un cycle de vie exploitable par #363.

Les exigences FAT/SAT/commissioning ne sont pas stockées directement dans les Stories. #363 possède ses propres `VerificationRequirement` et exécutions.

## Alternatives considered

### Fusionner Stories et Shift

Rejeté. Les deux concepts répondent à des questions différentes : travail technique à réaliser versus capacité réservée.

### Utiliser les Shift comme heures réalisées

Rejeté. Une réservation ne prouve pas une consommation réelle.

### Utiliser le restant Planning comme travail restant technique

Rejeté. Le restant Planning est un reliquat de capacité à affecter, pas un état d'exécution.

### Considérer les heures actuelles du WorkPackage comme budget approuvé

Rejeté tant qu'aucune autorité/version budgétaire explicite n'existe.

### Réutiliser planning_version pour le board Delivery

Rejeté pour les mutations purement Delivery. Cela couplerait inutilement deux domaines qui ne modifient pas le même état.

### Accorder manage_planning aux techniciens pour gérer le board

Rejeté. Les droits Delivery doivent être indépendants des mutations de capacité.

## Consequences

### Positive

- Planning reste stable et n'a pas à être refondu;
- la capacité, le travail restant et le budget ne sont pas confondus;
- la progression Delivery peut évoluer sans altérer Planning;
- les techniciens peuvent participer au board sans pouvoir modifier le planning;
- #363 peut se greffer sur des IDs Story stables;
- un futur budget Acumatica ou de vrais actuals peuvent être ajoutés sans redéfinir Delivery.

### Trade-offs / negative

- plusieurs indicateurs d'heures coexistent volontairement et doivent être clairement étiquetés;
- une projection Planning → Delivery doit maintenir une provenance explicite du plan actif;
- une version de concurrence Delivery supplémentaire est nécessaire;
- la progression pondérée exige une estimation de référence stable et une gestion claire des Stories non estimées;
- sans actuals réels, les comparaisons capacité ↔ restant restent des forecasts, pas de l'earned value.

## Implementation notes

#362 est découpée en :

1. 362A — contrats métier et règles pures;
2. 362B — persistance, versions et permissions Delivery;
3. 362C — commandes/API du board;
4. 362D — projection Planning et roll-up WorkPackage;
5. 362E — React Delivery/Kanban;
6. 362F — acceptation transversale, audit et non-régression.

Les migrations restent additives et portables SQLite/SQL Server.

Les formules de progression et forecast restent autoritaires côté backend.

## References

- GitHub Issue #362
- GitHub Issue #363
- GitHub Issue #364
- GitHub Issue #55
- GitHub Issue #13
- GitHub Issue #331
- ADR-003
- ADR-004
- ADR-006
- docs/FUTURE_DELIVERY_VERIFICATION.md
