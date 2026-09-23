# ADR-007 — Ressources réservables non humaines et occupation Planning commune

Status: Accepted  
Date: 2026-09-23

## Context

RessourcePlanner planifie aujourd'hui principalement des ressources humaines avec la chaîne :

```text
WorkforceRequest
└── RequestLine[WORKFORCE]
    └── ResourceRequirement
        └── Shift
```

L'issue #291 ajoute des ressources réservables non humaines : véhicules, nacelles, équipements, outils et, à terme, certains postes de travail.

Les décisions existantes restent applicables :

- ADR-001 sépare le besoin/cible automatique de l'affectation réelle;
- ADR-002 fixe les périodes au niveau de `RequestLine`;
- ADR-003 utilise une révision approuvée immuable comme preuve d'autorisation;
- ADR-004 sépare demande candidate, autorisation approuvée et plan actif;
- ADR-006 sérialise les mutations pertinentes du Planning par une révision globale persistante/CAS SQL.

Le moteur pur possède des primitives réutilisables de besoin, occupation verrouillée, capacité et comparaison, mais le parcours SQL/HTTP existant reste spécialisé pour les techniciens, les `ResourceRequirement` et les `Shift`.

Une ressource matérielle ne doit pas devenir un faux employé. Inversement, créer un moteur totalement séparé pour chaque catégorie d'actif dupliquerait les mécanismes de concurrence, d'approbation, d'audit et de projection déjà stabilisés.

La granularité temporelle est également structurante : le modèle humain actuel distribue des heures par jour et ne représente pas d'intervalles horaires permettant de prouver une exclusivité intrajournalière.

## Decision

### 1. Modèles persistants humains et actifs distincts

Les ressources humaines et les actifs restent des modèles persistants distincts.

Le parcours d'actifs est :

```text
WorkforceRequest
└── RequestLine[ASSET]
    └── AssetRequirement
        └── AssetAllocation

AssetType
└── Asset
    └── AssetAllocation
```

Il n'existe pas de super-entité SQL « ressource universelle ».

`ResourceProfile`, `ResourceRequirement` et `Shift` conservent leur sémantique humaine.

### 2. Une ligne possède une seule nature de besoin

Une `RequestLine` est soit `WORKFORCE`, soit `ASSET`.

Une même `WorkforceRequest` peut toutefois contenir simultanément plusieurs lignes humaines et matérielles.

Cette règle conserve une sémantique non ambiguë pour le budget, la quantité, les périodes, les alternatives et la matérialisation.

### 3. Besoin et allocation réelle restent séparés

`AssetRequirement` représente le besoin opérationnel matérialisé contre une autorisation approuvée.

`AssetAllocation.asset_id` représente l'unité physique réellement réservée.

Un besoin d'actif peut exister sans unité concrète encore sélectionnée. Il est alors visible comme besoin à affecter.

Une suggestion d'actif candidate ne constitue pas une réservation réelle.

### 4. Catalogue et identité des actifs

`AssetType` décrit le type métier réservable.  
`Asset` décrit une unité physique concrète identifiable.

Les deux utilisent des identités techniques stables. Les relations métier utilisent des IDs, jamais un nom d'affichage.

Les catégories telles que `VEHICLE`, `EQUIPMENT`, `TOOL` et éventuellement `WORKCENTER` restent des classifications, pas des sous-classes SQL.

La catégorie n'implique pas automatiquement une politique de capacité.

### 5. Granularité initiale : exclusivité à la journée

La première livraison #291 utilise une **occupation exclusive à la journée**.

Pour un `Asset` concret :

- une allocation qui occupe une date empêche toute autre allocation incompatible de ce même actif à cette date;
- une réservation de quelques heures ne libère pas automatiquement l'actif pour une seconde réservation le même jour;
- une immobilisation continue sur plusieurs dates occupe explicitement chacun des jours concernés;
- aucune garantie d'exclusivité horaire fine n'est fournie.

Le partage intrajournalier et les intervalles `start_time/end_time` sont hors scope initial.

### 6. Budget d'utilisation et occupation physique sont distincts

Les heures d'actifs restent explicites lorsqu'elles sont nécessaires au budget ou aux projections.

Elles ne reçoivent aucun défaut humain implicite de 8 h/jour.

Une heure d'utilisation n'est pas l'unité utilisée pour prouver l'exclusivité physique. Le moteur d'heures ne doit pas recevoir une fausse capacité de `1` pour simuler une unité matérielle.

Les heures humaines et les heures d'actifs ne sont pas additionnées dans un même indicateur de charge humaine.

### 7. Affectation explicite dans #291

La première livraison n'effectue pas de sélection automatique parmi plusieurs unités interchangeables.

Le coordonnateur choisit explicitement l'actif concret.

Le système peut recommander ou filtrer des candidats plus tard, mais un rebuild ne doit jamais substituer silencieusement une autre unité à une allocation existante.

### 8. Quantité par lignes/slots indépendants

Le besoin de plusieurs unités réutilise la logique de lignes/slots indépendants de #288.

Un besoin collectif indivisible du type « trois actifs exactement simultanés » n'est pas ajouté implicitement à #291.

### 9. Même orchestration Planning, pas de moteur autonome par catégorie

Les modèles persistants sont distincts, mais les comportements transversaux restent communs lorsqu'ils portent réellement la même sémantique :

- transaction;
- `planning_version` / CAS;
- idempotence;
- audit;
- préparation preview/exécution;
- comparaison de plans;
- conservation des décisions manuelles/verrouillées;
- validation d'un état projeté;
- capacité/occupation lorsque les unités sont compatibles.

Restent spécifiques :

- horaires, congés et hors horaire humains;
- placement exclusif d'un actif;
- sélection automatique d'une unité;
- qualification d'un opérateur;
- communications et vues propres aux personnes.

Un succès composite doit rester dans une seule transaction et ne déclencher qu'une orchestration de rebuild nécessaire.

### 10. Approbation et périodes communes

Les lignes `ASSET` réutilisent les périodes et alternatives de `RequestLine`.

L'identité logique reste notamment fondée sur la ligne et la période, sans second modèle de périodes.

Une révision approuvée doit capturer les contraintes d'actifs nécessaires pour constituer une preuve d'autorisation, notamment :

- `line_kind = ASSET`;
- `asset_type_id`;
- slots;
- fenêtres exactes;
- heures autorisées et leur sémantique;
- politique d'occupation;
- contexte projet/site/tâche/WorkPackage;
- alternatives autorisées.

Le format de snapshot approuvé évolue de manière versionnée. Les anciennes révisions restent lisibles et leur empreinte historique n'est pas recalculée selon la nouvelle version.

Changer l'unité concrète pour une autre unité admissible du même type peut rester opérationnel. Changer de type, ajouter un slot, sortir de la fenêtre ou modifier la portée reste soumis à la politique d'enveloppe.

Comme pour #333, approuver une nouvelle fenêtre n'exécute pas un ancien geste de déplacement/allocation.

### 11. Même révision globale de Planning

Les mutations d'actifs qui influencent le plan participent à ADR-006.

Cela inclut notamment :

- réservation;
- déplacement;
- changement d'actif;
- libération/annulation;
- changement de budget/cible pertinent;
- approbation ou sélection opérationnelle;
- indisponibilité/désactivation qui affecte une réservation;
- changement de type ou politique d'occupation pertinent.

Aucun compteur, mutex ou système de version parallèle propre aux actifs n'est ajouté.

Un conflit physique de double réservation n'est pas une exception budgétaire : `KEEP_EXCEPTION` ne permet jamais d'occuper physiquement deux fois le même actif.

### 12. Disponibilité et conflits

La disponibilité d'un actif appartient au modèle d'actif et non à `ResourceAvailabilityRule` humain.

Une allocation tentative d'un actif concret consomme sa disponibilité.

Si une indisponibilité est créée alors qu'une réservation existe déjà, la réservation n'est pas supprimée silencieusement : le système conserve l'état et expose un conflit à résoudre.

### 13. Frontière avec #292

#291 prépare des identités stables d'actifs et d'allocations, une provenance fiable, des dates d'occupation et des commandes atomiques auditables.

#292 possède les règles de qualification :

- `AssetType ↔ Competency`;
- opérateur humain qualifiant lié à une `AssetAllocation`;
- validation d'activité, compétence et chevauchement avec les affectations humaines;
- diagnostics de qualification;
- revalidation et règles de communication.

Le catalogue de compétences de #272 est réutilisé; aucun référentiel parallèle « permis » n'est créé.

### 14. WORKCENTER partagé différé

Le contrat doit permettre une évolution future vers `WORKCENTER`.

Un poste physique individuel exclusif peut utiliser la notion d'unité réservable.

Une capacité partagée/divisible d'atelier ou d'équipe pourra nécessiter une politique différente. #291 ne transforme pas le Planning en MES et n'introduit pas maintenant routages, gammes, précédences, changements de série ou optimisation de séquences.

## Alternatives considered

### Super-entité SQL Resource pour humains et actifs

Rejetée. Elle mélangerait identité humaine, disponibilité matérielle, OIDC, compétences, horaires et réservation physique dans une hiérarchie artificielle.

### Réutiliser ResourceRequirement et Shift pour les actifs

Rejeté. Ces modèles portent des clés étrangères et des comportements humains. Cela créerait de faux techniciens ou des relations polymorphes ambiguës.

### Moteur Planning entièrement séparé pour les actifs

Rejeté. Les actifs doivent réutiliser l'approbation, la concurrence, l'idempotence, l'audit et les projections communes. Seules les règles spécifiques de placement restent distinctes.

### Capacité horaire quotidienne

Non retenue pour la première livraison. Elle permettrait de comparer des heures mais ne prouverait pas l'absence de chevauchement réel dans la journée.

### Intervalles horaires exacts

Différés. Ils nécessiteraient un nouveau contrat temporel, des règles de chevauchement et des changements importants du Planning.

### Sélection automatique d'une unité interchangeable

Différée. Le moteur actuel reçoit une cible; il ne résout pas encore déterministement le choix d'une unité parmi un catalogue interchangeable tout en conservant les décisions manuelles.

## Consequences

### Positive

- aucun faux employé n'est créé;
- le modèle demande → besoin → allocation reste cohérent avec les décisions existantes;
- demandes humaines, matérielles et mixtes partagent le même workflow d'approbation;
- la concurrence globale et les transactions restent uniformes;
- les règles matérielles n'altèrent pas les règles d'horaires humains;
- #292 peut ajouter les opérateurs qualifiés sans coupler l'actif à un `Shift` automatique;
- l'architecture laisse une voie vers `WORKCENTER` sans imposer une capacité partagée prématurément.

### Trade-offs / negative

- le Planning devra supporter des projections et commandes typées plutôt qu'une seule collection universelle;
- certaines abstractions communes devront transporter explicitement leur unité de capacité/occupation;
- l'exclusivité à la journée est volontairement conservatrice;
- un actif réservé quelques heures n'est pas réutilisable le même jour dans la première livraison;
- l'affectation d'une unité reste manuelle;
- les snapshots approuvés nécessitent une nouvelle version de format;
- les migrations sont additives mais traversent plusieurs projections et read models.

## Implementation notes

#291 est découpé en :

1. 291A — contrats et frontières pures;
2. 291B — catalogue et persistance;
3. 291C — demande, approbation et matérialisation;
4. 291D — réservations et concurrence;
5. 291E — projections et delta;
6. 291F — React et acceptation.

Les migrations doivent rester additives, portables SQLite/SQL Server et ne doivent ni backfiller des actifs fictifs ni reconstruire les données humaines existantes.

Les APIs humaines existantes doivent conserver leur sens. Des lectures/commandes d'actifs explicites sont préférables à une réinterprétation silencieuse de `resources/shifts/segments`.

## References

- GitHub Issue #291
- GitHub Issue #292
- GitHub Issue #55
- GitHub Issue #13
- GitHub Issue #38
- GitHub Issue #272
- GitHub Issue #288
- GitHub Issue #331
- GitHub Issue #332
- GitHub Issue #333
- ADR-001
- ADR-002
- ADR-003
- ADR-004
- ADR-006
