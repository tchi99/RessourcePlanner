# ADR-006 — Révision globale des mutations de planning

Status: Accepted  
Date: 2026-09-22

## Context

#332 introduit des commandes composites de partage et duplication de `Shift`.

Le planning actuel est recalculé globalement : `rebuild()` peut supprimer et recréer des sorties automatiques au-delà du seul `ResourceRequirement` directement muté. Une commande qui valide un budget ou une surallocation à partir d'un état lu sans protection commune peut donc être invalidée par une autre écriture concurrente avant son commit.

Les protections existantes ne couvrent pas cette frontière :

- `Shift` et `ResourceRequirement` n'ont pas de version de mutation autoritaire;
- `WorkforceRequest.aggregate_version` versionne la demande, pas le plan actif;
- `RequestOperationalState.version` protège certains choix opérationnels avec CAS, mais pas l'ensemble du planning;
- un verrou pris uniquement dans `rebuild()` arrive trop tard, après les lectures et validations décisionnelles;
- un mutex Python ne protège pas plusieurs processus/instances.

Une version du seul quart source est également insuffisante : deux opérations sur deux sources différentes du même besoin peuvent chacune valider le même budget disponible.

ADR-001, ADR-003 et ADR-004 restent applicables. Cette décision ne change ni le modèle besoin/quart, ni la séparation candidat/approuvé/actif.

## Decision

Tant que le rebuild reste global, RessourcePlanner utilise une **révision persistante globale des mutations de planning** comme garde de concurrence commune.

L'implémentation introduit de façon additive un état persistant monotone du planning. Les commandes concernées :

1. reçoivent ou résolvent un `expected_planning_version`;
2. rejouent d'abord un éventuel résultat idempotent déjà validé;
3. acquièrent conditionnellement la révision par une écriture SQL CAS **avant les lectures décisionnelles**;
4. effectuent validation, mutations, flush, rebuild éventuel, invariants, audit et reçu idempotent dans la même transaction;
5. laissent le commit/rollback à la transaction englobante.

Une acquisition CAS perdue retourne un conflit structuré et ne poursuit pas l'opération contre un état périmé.

La révision globale couvre les mutations qui peuvent concurrencer les décisions de planning, notamment :

- création/édition/déplacement/suppression/release de quarts;
- mutations de besoin ou budget opérationnel;
- changement de cible automatique;
- approbation/resynchronisation qui matérialise le plan;
- choix opérationnels affectant la matérialisation ou le budget;
- rebuild de support;
- autres mutations de capacité qui influencent le même calcul lorsque leur chemin est transactionnellement pertinent.

Les CAS plus spécifiques déjà utiles, notamment `RequestOperationalState.version`, sont conservés. La version globale ne les remplace pas lorsqu'ils protègent une sémantique locale distincte.

Pour une opération liée à une demande approuvée, la commande vérifie également la référence d'autorisation active pertinente (`approval_revision_id`, `approved_entry_key`) et la version opérationnelle attendue lorsqu'elle modifie ces choix.

La version de la **demande candidate** n'est pas une dépendance d'une opération strictement exécutée contre l'ancienne autorisation et le plan actif. Une modification descriptive candidate ne doit pas provoquer artificiellement un conflit de planning.

## Transaction boundary

Pour une commande composite telle que #332, la transaction couvre l'intégralité de l'opération, y compris le rebuild global :

```text
idempotency replay
→ acquire global planning revision (CAS)
→ reread + validate authoritative state
→ build projected final state
→ mutate source/target/budget
→ flush
→ rebuild exactly once
→ verify final invariants
→ audit + idempotency receipt
→ commit
```

Aucun adaptateur interne ne fait de `commit()`.

Un échec après le rebuild doit donc restaurer non seulement les quarts directement touchés, mais aussi les sorties automatiques d'autres besoins modifiées par ce rebuild.

## Idempotency interaction

Le replay idempotent est vérifié avant le rejet d'une ancienne version, car un premier succès peut légitimement avoir rendu `expected_planning_version` périmé.

Pour une course simultanée utilisant la même clé :

- un seul appel peut acquérir/appliquer la mutation;
- l'appel perdant doit pouvoir retrouver le reçu du succès correspondant;
- il ne doit pas réexécuter aveuglément la commande;
- même clé avec fingerprint différent reste un conflit.

Les nouvelles commandes doivent utiliser une identité authentifiée stable pour la portée d'idempotence plutôt qu'un simple nom d'affichage.

## Alternatives considered

### Versionner uniquement chaque Shift

Rejeté pour cette tranche. Deux sources différentes sous le même besoin peuvent consommer le même budget en parallèle. Cela ne protège pas non plus les effets globaux du rebuild.

### Versionner Shift + ResourceRequirement séparément

Possible à terme, mais insuffisant sans protocole commun avec approbation, choix opérationnels et rebuild. Cela introduirait plusieurs systèmes de versions et une orchestration plus complexe alors que le recalcul est encore global.

### Verrouiller uniquement dans rebuild()

Rejeté. Les lectures de budget, de surallocation et d'autorisation auraient déjà été effectuées sans protection.

### Mutex/process lock Python

Rejeté. Il ne fournit aucune garantie entre plusieurs processus ou instances du serveur.

### Isolation sérialisable globale de la base

Non retenue comme contrat applicatif. Elle est plus large, dépend davantage du dialecte/configuration et n'expose pas naturellement un jeton de concurrence au client.

## Consequences

### Positive

- une commande peut savoir que l'état utilisé pour sa décision n'a pas été modifié par une autre mutation participante;
- les opérations composites #332 peuvent garantir budget et surallocation sous concurrence;
- le client dispose d'un jeton explicite pour détecter un snapshot périmé;
- le protocole reste compatible avec SQLite local et SQL Server cible;
- une seule primitive de concurrence est alignée avec la portée actuelle du rebuild global.

### Trade-offs

- deux utilisateurs travaillant sur des besoins indépendants peuvent entrer en conflit même si leurs objets ne se chevauchent pas;
- toutes les mutations concurrentes pertinentes doivent participer au protocole, sinon la garantie serait incomplète;
- les tests SQLite séquentiels ne démontrent pas à eux seuls la garantie SQL Server;
- si le rebuild devient plus fin à l'avenir, une granularité de version plus locale pourra devenir pertinente.

Le compromis de conflits plus larges est accepté pour #332 parce qu'il correspond à la portée réellement globale du recalcul actuel.

## Implementation sequence

#332A implémente cette décision avant les commandes split/duplicate :

1. migration additive et état global de révision;
2. port/repository de lecture + acquisition CAS;
3. exposition du `planning_version` dans les read models nécessaires;
4. raccord des mutations concurrentes pertinentes;
5. conflits structurés;
6. tests avec deux sessions/transactions;
7. validations SQLite + SQL Server readiness.

La validation réelle multi-session sur SQL Server cible est complétée dans #162. Elle ne bloque pas l'implémentation locale de 332A, mais elle reste nécessaire avant de présenter la garantie comme validée sur la cible de production.

## References

- GitHub Issue #332
- GitHub Issue #55
- GitHub Issue #13
- GitHub Issue #38
- GitHub Issue #162
- GitHub Issue #331
- ADR-001
- ADR-003
- ADR-004


## Extension #333 — fenêtre + déplacement

#333 applique la même frontière transactionnelle aux gestes DnD qui peuvent élargir la
fenêtre d'un besoin. L'évaluation préalable est strictement en lecture seule et ne
réserve aucune capacité. La commande d'exécution :

1. rejoue d'abord un reçu idempotent existant;
2. acquiert le `planning_version` global avant toute lecture décisionnelle;
3. relit le `Shift`, le `ResourceRequirement`, la ressource cible et, pour une
   origine `REQUEST`, l'entrée locale de la révision approuvée active;
4. n'autorise l'extension immédiate que si la date cible appartient à cette entrée
   approuvée exacte; une fenêtre globale min/max de la demande ne constitue pas une
   autorisation;
5. écrit l'élargissement minimal de fenêtre et le déplacement comme une seule mutation;
6. convertit le quart déplacé en décision manuelle verrouillée, reconstruit exactement
   une fois, vérifie les invariants, journalise la fenêtre et le quart, puis produit le
   reçu idempotent dans la transaction englobante.

Une cible hors enveloppe approuvée n'exécute jamais l'ancien geste après approbation :
elle modifie uniquement la proposition candidate via ADR-004. Aucun intent de
déplacement durable n'est créé; après approbation, l'utilisateur initie un nouveau geste
contre le `planning_version`, la révision approuvée et la version opérationnelle frais.
