# ADR-003 — Révision approuvée immuable comme preuve d'autorisation

Status: Accepted  
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

La politique peut autoriser une **tolérance déléguée d'effort** selon l'acteur sans altérer la révision approuvée de référence. Pour un `PROJECT_MANAGER`, cette tolérance est fixée à **+20 % inclusivement** du budget approuvé local du besoin concerné. Le plafond est toujours calculé depuis la dernière révision approuvée, jamais depuis une valeur déjà augmentée par tolérance; les hausses ne se composent donc pas entre elles.

La tolérance déléguée ne couvre que l'effort/heures dans la même portée approuvée. Elle ne couvre pas les changements de fenêtre, projet, site, type/classe, compétences, tâche/WorkPackage, ajout de ligne/période cumulative ou consommation simultanée d'alternatives exclusives.

`ADMIN` et `COORDINATOR`, déjà détenteurs de l'autorité d'approbation, ne repassent pas par un second workflow lorsqu'ils élargissent eux-mêmes l'autorisation. Une hausse durable crée toutefois une nouvelle révision approuvée immuable et auditée, activée atomiquement.

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

## Delegated tolerance and KEEP_EXCEPTION

La décision PO est fixée :

- un `PROJECT_MANAGER` peut augmenter l'effort/heures d'un besoin jusqu'à **+20 % inclusivement** de la dernière révision approuvée locale, sans réapprobation;
- au-delà de +20 %, `REAPPROVAL_REQUIRED` s'applique et l'approbation d'un `COORDINATOR` ou `ADMIN` est requise;
- la tolérance est locale au besoin et ne peut pas être transférée entre lignes, périodes ou groupes;
- le plafond ne se compose jamais : une base approuvée de 100 h reste plafonnée à 120 h tant qu'aucune nouvelle révision n'est approuvée;
- les changements de portée restent soumis à réapprobation même sous 20 %;
- `ADMIN` et `COORDINATOR` n'ont pas à s'auto-réapprouver; une hausse durable de l'autorisation crée directement une nouvelle révision approuvée atomique et auditée.

`KEEP_EXCEPTION` reste distinct d'une augmentation durable de l'autorisation : il conserve le budget approuvé et accepte explicitement un excédent verrouillé. Il doit rester visible, justifié/audité et ne réécrit jamais silencieusement la révision approuvée.

La politique peut conserver `WITHIN_ENVELOPE` comme résultat contractuel pour une hausse PM tolérée, avec une raison telle que `DELEGATED_TOLERANCE`, afin d'exposer clairement la base approuvée, la valeur proposée, la variation et l'acteur.

## References

- GitHub Issue #13
- GitHub Issue #38
- GitHub Issue #55
- GitHub Issue #288
- GitHub Issue #331
- ADR-001
- ADR-002
