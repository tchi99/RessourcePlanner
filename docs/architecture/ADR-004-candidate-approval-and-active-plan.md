# ADR-004 — Séparer proposition candidate, autorisation approuvée et plan actif

Status: Proposed  
Date: 2026-09-22

## Context

Lorsqu'une demande approuvée est modifiée, RessourcePlanner doit conserver l'ancien plan opérationnel jusqu'à la nouvelle approbation.

En parallèle, certaines opérations sont légitimes sans réapprobation : confirmer une période déjà autorisée, sélectionner une autre alternative approuvée, modifier la répartition opérationnelle dans les fenêtres autorisées ou changer une cible automatique sans modifier l'autorisation métier.

Une unique représentation mutable ne suffit pas à distinguer :

- la proposition en cours d'édition;
- ce qui est officiellement autorisé;
- ce qui est effectivement actif dans le plan.

Les protections des quarts verrouillés doivent également être identiques quel que soit le chemin de synchronisation.

## Decision

RessourcePlanner maintient trois états distincts :

1. **demande candidate** — définition proposée et éditable;
2. **révision approuvée active** — preuve immuable de ce qui est autorisé;
3. **plan opérationnel actif** — besoins matérialisés, choix opérationnels et quarts réels.

Les sélections d'alternatives et confirmations opérationnelles sont contextualisées par l'autorisation active et ne doivent pas être confondues avec des choix candidats encore non approuvés.

Une resynchronisation dans l'enveloppe s'appuie sur la révision approuvée active et sur les choix opérationnels actifs. Elle ne relit pas silencieusement toute la demande candidate.

Une réapprobation active une nouvelle révision de manière transactionnelle :

1. validation des versions;
2. validation de la proposition;
3. validation des verrous et de la faisabilité;
4. création de la révision;
5. matérialisation;
6. recalcul;
7. bascule de la référence active;
8. audit.

En cas d'échec, aucune bascule partielle n'est conservée.

Les mutations de périodes, sélections et opérations sensibles utilisent des versions attendues et signalent les conflits explicitement.

Le moteur de planification reste ignorant du workflow d'approbation. Une couche de préparation commune transforme l'autorisation et les choix opérationnels en spécifications planifiables pour :

- approbation;
- sélection opérationnelle;
- réapprobation;
- preview / plan delta;
- projections de charge pertinentes.

Les quarts verrouillés sont protégés avant toute resynchronisation, y compris dans les parcours historiques.

## Operational rules

Par défaut :

- une confirmation seule à l'intérieur de l'enveloppe est une mutation opérationnelle auditée sans réapprobation;
- sélectionner une autre alternative déjà approuvée est opérationnel, sous réserve des verrous;
- modifier le plan actif pendant qu'une réapprobation est en attente reste permis uniquement contre l'ancienne révision approuvée active;
- une réduction opérationnelle temporaire peut conserver l'autorisation initiale;
- une réduction définitive du besoin modifie la proposition et suit le workflow de réapprobation;
- projet, site, type/classe, compétences, tâche/WorkPackage et effort sont structurants par défaut;
- les jours actifs restent une préférence de distribution;
- une ressource proposée reste une suggestion et non une contrainte d'autorisation;
- les ressources réellement affectées restent portées par `Shift.resource_id` conformément à ADR-001.

## Alternatives considered

### Modifier immédiatement le plan puis corriger après réapprobation

Rejeté. Une proposition non autorisée ne doit jamais devenir temporairement le plan actif.

### Bloquer tout changement opérationnel pendant une réapprobation

Rejeté. Cela figerait inutilement l'exploitation alors que l'ancienne autorisation reste valide.

### Cloner l'intégralité du plan pour chaque proposition

Non retenu pour #13. Le besoin principal est de versionner l'autorisation et les choix opérationnels nécessaires, pas chaque sortie automatique du moteur.

### Utiliser la sélection candidate comme sélection active

Rejeté. Cela permettrait à une modification non approuvée de modifier le plan avant approbation.

## Consequences

### Positive

- l'exploitation peut continuer pendant une réapprobation;
- une modification candidate ne double pas la charge du plan actif;
- confirmation et sélection peuvent évoluer sans réapprobation lorsqu'elles restent autorisées;
- les previews et deltas peuvent distinguer besoin, affectations et autorisation;
- les protections de verrous deviennent cohérentes;
- #332/#333 disposent d'une frontière claire pour leurs intentions de planning.

### Trade-offs / negative

- les sélections actives et candidates doivent être distinguées;
- la concurrence doit être gérée explicitement;
- les previews doivent être revalidés lors de l'exécution;
- certaines routes historiques par demande devront converger vers les contrats par ligne.

## Open decision

La manière exacte dont `KEEP_EXCEPTION` interagit avec l'enveloppe approuvée reste à décider.

Une exception ne doit jamais être présentée comme une augmentation silencieuse de l'autorisation approuvée. Si elle est permise, elle doit rester distincte, explicite et auditée.

## References

- GitHub Issue #13
- GitHub Issue #38
- GitHub Issue #55
- GitHub Issue #331
- GitHub Issue #332
- GitHub Issue #333
- ADR-001
- ADR-002
- ADR-003
