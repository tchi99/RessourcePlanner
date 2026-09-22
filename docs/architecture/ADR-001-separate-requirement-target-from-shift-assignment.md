# ADR-001 — Séparer la cible automatique du besoin de l'affectation réelle des quarts

Status: Accepted  
Date: 2026-09-22

## Context

Le modèle SQL autorise déjà plusieurs `Shift` de ressources différentes sous un même
`ResourceRequirement`, mais `ResourceRequirement.assigned_resource_id` a historiquement
servi à la fois de cible de génération automatique et de représentation de l'affectation
du besoin.

Cette ambiguïté provoque notamment deux effets indésirables :

- déplacer ou éditer un quart peut réorienter implicitement le reliquat automatique;
- un quart verrouillé peut devenir invisible au calcul de capacité lorsque son besoin
  n'a pas de cible automatique planifiable.

L'issue #331 doit clarifier ces responsabilités sans refondre les relations de
planification ni introduire une nouvelle table d'affectation.

## Decision

`ResourceRequirement` représente le besoin planifiable et son budget.

`ResourceRequirement.assigned_resource_id` conserve temporairement son nom de colonne
mais sa sémantique autoritaire est **la ressource cible de la génération automatique du
reliquat**. Ce champ n'est pas la vérité des affectations réellement effectuées.

`Shift.resource_id` est la vérité autoritaire de la ressource réellement affectée à
un quart.

Conséquences opérationnelles :

- un besoin peut avoir des quarts sur plusieurs ressources;
- un quart verrouillé actif consomme toujours la capacité de son propre
  `Shift.resource_id`, même lorsque le besoin n'a aucune cible automatique générable;
- créer, éditer ou déplacer un quart ne doit pas modifier implicitement la cible
  automatique du besoin;
- changer la cible automatique reste une commande métier explicite distincte;
- les projections doivent distinguer la cible automatique des ressources réellement
  mobilisées;
- les communications relatives à un quart utilisent la ressource réelle du quart;
- une différence entre la cible du besoin et la ressource d'un quart n'est pas une
  anomalie par elle-même.

Le renommage physique de `assigned_resource_id` est différé afin de préserver la
compatibilité et d'éviter une migration de schéma non nécessaire à #331.

## Alternatives considered

### Maintenir « un besoin = une ressource »

Rejeté. Le modèle et les usages actuels permettent déjà plusieurs ressources réelles
sous un même besoin, et cette contrainte rendrait le partage manuel artificiellement
impossible.

### Introduire une nouvelle entité d'affectation entre besoin et quart

Rejeté pour #331. `Shift` porte déjà l'affectation réelle avec son identité, sa date,
ses heures et son verrouillage. Une nouvelle relation dupliquerait une information
existante sans besoin démontré.

### Renommer immédiatement `assigned_resource_id`

Différé. Le nouveau sens doit être explicite dans les contrats et projections, mais un
renommage SQL ajouterait une migration et un coût de compatibilité sans apporter de
garantie métier supplémentaire dans cette tranche.

## Consequences

### Positive

- la cible automatique et les affectations réelles deviennent deux concepts explicites;
- les décisions manuelles multi-ressources survivent au recalcul;
- la capacité est calculée à partir des ressources réellement engagées;
- le drag-and-drop futur peut déplacer un quart sans déplacer silencieusement le reste
  du besoin;
- aucune nouvelle table ni migration destructive n'est requise.

### Trade-offs / negative

- le nom historique `assigned_resource_id` reste temporairement moins précis que sa
  sémantique;
- les anciens contrats utilisant `resource_name` doivent être maintenus pendant une
  période de compatibilité;
- les consommateurs doivent choisir explicitement entre cible automatique et ressource
  réelle selon leur contexte.

## Implementation notes

#331 est livré par étapes :

1. métriques et projections canoniques;
2. capacité des quarts verrouillés indépendante de la cible;
3. séparation des commandes de quart et de changement de cible;
4. adaptation des consommateurs métier et du delta;
5. intégration React et tests transversaux.

La conservation individuelle des quarts automatiques entre deux rebuilds ne fait pas
partie de cette décision : les sorties automatiques restent remplaçables par le moteur.

## References

- GitHub Issue #331
- GitHub Issue #55
- GitHub Issue #289
- GitHub Issue #275
- PR #335 — 331A
