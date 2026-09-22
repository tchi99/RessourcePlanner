# ADR-002 — Périodes par ligne et identités stables du besoin demandé

Status: Accepted  
Date: 2026-09-22

## Context

Après #288, une `WorkforceRequest` peut contenir plusieurs `RequestLine` hétérogènes. Le dépôt possède déjà des périodes persistantes, des groupes alternatifs exclusifs et des identités logiques de période.

#13 doit consolider cette architecture sans recréer un second modèle de périodes ni déplacer les alternatives vers les besoins matérialisés.

Les alternatives non sélectionnées doivent exister avant matérialisation, tandis que les `ResourceRequirement` ne représentent que les besoins effectivement matérialisés.

## Decision

Les périodes persistantes restent représentées par `WorkforceRequestPeriod`, mais leur propriétaire métier canonique est `RequestLine`.

Le lien vers `WorkforceRequest` peut être conservé pour les requêtes, la compatibilité et la navigation d'agrégat, à condition que le backend garantisse que la période, la ligne et la demande appartiennent au même agrégat.

Les identités canoniques sont :

| Élément | Identité |
|---|---|
| Ligne | `RequestLine.id` |
| Période logique | `(request_line_id, period_key)` |
| Version persistante de période | `WorkforceRequestPeriod.id` |
| Groupe alternatif exclusif | `(request_line_id, group_key)` |
| Besoin matérialisé | `ResourceRequirement.id` + provenance approuvée |
| Quart réel | `Shift.id` |

`group_key` est une identité stable et ne dépend pas du libellé présenté à l'utilisateur.

Une ligne simple sans périodes explicites n'exige pas une ligne SQL artificielle. Le backend produit une représentation normalisée équivalente à partir de ses dates/heures.

Lorsqu'une ligne possède des périodes détaillées, ses champs simples servent de valeurs par défaut ou de résumé. Ils ne constituent jamais un budget additionnel.

Les périodes cumulatives s'additionnent. Les options d'un même groupe alternatif sont exclusives et ne doivent pas être double-comptées.

## Alternatives considered

### Périodes uniquement sur WorkforceRequest

Rejeté. Cette structure ne représente pas correctement les fenêtres et contraintes propres à plusieurs `RequestLine` hétérogènes.

### Périodes uniquement sur ResourceRequirement

Rejeté. Les alternatives non sélectionnées doivent exister avant qu'un besoin opérationnel soit matérialisé.

### Nouveau modèle parallèle de périodes

Rejeté. Le dépôt possède déjà les objets persistants, les clés logiques et les règles de non-double-comptage nécessaires.

### Créer systématiquement une période SQL pour toute ligne simple

Non retenu pour #13. Une normalisation en mémoire suffit et évite une migration de données sans besoin démontré.

## Consequences

### Positive

- aucune refonte inutile du modèle de périodes;
- les lignes multi-besoins de #288 restent la frontière métier correcte;
- les alternatives peuvent être approuvées même lorsqu'elles ne génèrent aucun besoin actif;
- les identités survivent aux renommages et réordonnancements;
- #329/#330 peuvent exposer périodes et groupes par ligne sans reconstruire leur sémantique.

### Trade-offs / negative

- le schéma conserve temporairement un lien de période à la demande en plus du lien à la ligne;
- les parcours historiques par demande doivent progressivement converger vers les contrats par ligne;
- les consommateurs doivent distinguer identité logique et version physique.

## Implementation notes

#13A doit fournir la normalisation pure utilisée par les comparaisons d'enveloppe.

#13H raccorde React aux périodes par ligne, mais la refonte complète du détail de demande reste #330.

Les jours actifs restent une préférence de distribution tant qu'une décision métier explicite ne les transforme pas en contrainte contractuelle dure.

## References

- GitHub Issue #13
- GitHub Issue #55
- GitHub Issue #288
- GitHub Issue #331
- ADR-001
