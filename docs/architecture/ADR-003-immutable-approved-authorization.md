# ADR-003 — Révision approuvée immuable comme preuve d'autorisation

Status: Proposed  
Date: 2026-09-22

## Context

Une demande approuvée peut ensuite être modifiée et revenir en réapprobation alors que l'ancien plan actif doit rester exploitable.

L'état courant de la demande ne constitue donc pas une référence fiable pour décider si une mutation opérationnelle reste dans ce qui avait été approuvé.

L'historique actuel ne conserve pas toutes les valeurs nécessaires pour reconstruire chaque révision approuvée, et les `ResourceRequirement` ne capturent pas les alternatives non sélectionnées.

#13 a besoin d'une preuve d'autorisation indépendante de la demande candidate et du plan opérationnel.

## Decision

Chaque approbation crée une nouvelle entité immuable de type `RequestApprovalRevision`.

Cette révision capture au minimum :

- la demande et sa version approuvée;
- l'approbateur, la date, la provenance et la version de format;
- le projet et la portée métier;
- les lignes et leurs identités;
- type, classe et compétences par IDs stables;
- références de tâche et WorkPackage pertinentes;
- fenêtres exactes;
- heures et règles de jours actifs;
- toutes les périodes;
- toutes les options alternatives autorisées, y compris celles non sélectionnées;
- l'exclusivité et les limites des groupes;
- les valeurs de confirmation et de sélection au moment de l'approbation comme trace.

La confirmation et la sélection capturées ne deviennent pas des contraintes immuables : leurs évolutions opérationnelles sont gérées séparément tant qu'elles demeurent autorisées par la révision.

La persistance privilégiée est :

- une table relationnelle de révisions avec métadonnées et références;
- un payload canonique, typé et versionné sérialisé dans un type portable `Text`;
- une référence de révision sur les besoins matérialisés;
- une clé stable de l'entrée autorisée à laquelle chaque besoin se rattache.

Le snapshot approuvé est la preuve d'autorisation. Les besoins et quarts sont l'état opérationnel résultant, pas un substitut à cette preuve.

Une politique backend commune compare les mutations à la révision active et retourne un résultat structuré parmi :

- `WITHIN_ENVELOPE`;
- `REAPPROVAL_REQUIRED`;
- `EXPLICIT_EXCEPTION_REQUIRED`;
- `APPROVAL_REFERENCE_UNKNOWN`;
- `INVALID`.

L'enveloppe conserve sa topologie locale : budgets, fenêtres, lignes, groupes, alternatives et qualifications. Elle n'est pas réduite à un total global transférable.

## Alternatives considered

### Comparer à la demande courante

Rejeté. Une demande candidate pourrait alors s'autoriser elle-même avant réapprobation.

### Reconstruire l'approbation depuis les ResourceRequirement

Rejeté. Les alternatives non matérialisées et certaines contraintes approuvées n'y existent pas.

### Rejouer uniquement l'historique de demande

Rejeté. L'historique actuel n'est pas un event store complet et ne contient pas toutes les valeurs nécessaires.

### Versionner intégralement tous les brouillons

Non retenu pour #13. La demande courante peut rester la proposition éditable; seule la preuve d'approbation doit être immuable.

### Décomposer entièrement le snapshot en tables relationnelles

Différé. Ce serait possible, mais disproportionné tant que les comparaisons restent effectuées dans le domaine Python. Le payload `Text` garde SQLite/SQL Server portables sans dépendre d'opérateurs JSON spécifiques.

## Consequences

### Positive

- une mutation peut être comparée à ce qui a réellement été approuvé;
- une proposition hors enveloppe n'altère pas le plan actif;
- les alternatives non sélectionnées restent représentées dans l'autorisation;
- les règles de réapprobation deviennent communes aux formulaires et aux commandes directes;
- l'historique d'approbation devient explicite et auditable;
- #329 peut exposer candidat, approuvé et actif séparément.

### Trade-offs / negative

- une nouvelle table et une migration additive sont nécessaires;
- le payload doit être versionné et validé par le domaine;
- les anciennes approbations ne peuvent pas toujours être reconstruites automatiquement;
- les commandes qui modifient budgets/fenêtres doivent consulter la politique commune.

## Historical data

Les données historiques dont l'autorisation complète ne peut pas être prouvée utilisent un état explicite `LEGACY_UNKNOWN`.

Pour ces données :

- le plan existant est conservé;
- les opérations démontrablement valides peuvent continuer;
- un élargissement ne peut pas être présenté comme déjà approuvé;
- une nouvelle approbation régularise la référence.

La migration ne force pas une réapprobation générale.

## Open decision

La politique finale de `KEEP_EXCEPTION` reste une décision PO ouverte.

#38 permet aujourd'hui de conserver explicitement des quarts verrouillés au-delà de `planned_hours`. #13 doit décider quels rôles peuvent autoriser cette exception et jusqu'où elle peut dépasser l'enveloppe approuvée.

Tant que cette décision n'est pas prise, la politique peut retourner `EXPLICIT_EXCEPTION_REQUIRED`, mais ne doit pas inventer l'autorisation finale.

## References

- GitHub Issue #13
- GitHub Issue #38
- GitHub Issue #55
- GitHub Issue #288
- GitHub Issue #331
- ADR-001
- ADR-002
