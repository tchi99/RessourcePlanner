# Pré-cutover — invariants du modèle opérationnel

Ce document fixe les invariants fonctionnels qui doivent rester vrais pendant le passage Excel/NiceGUI vers SQL/FastAPI/React.

Il est aligné sur le modèle actuel après #13, #328, #329 et #331. Les ADR sous `docs/architecture/` restent autoritaires lorsqu'une décision y est formalisée.

## Propriété des données

- `Project` porte le contexte projet et ses références métier.
- `WorkforceRequest` est l'entête de workflow : projet, demandeur canonique, priorité, description, statut et version d'agrégat.
- `RequestLine` est la frontière canonique du besoin demandé planifiable : classe/compétences, dates, effort, confirmation, tâche ERP, WorkPackage, ressource proposée et description.
- Le schéma conserve certains champs historiques sur `WorkforceRequest` pour compatibilité; ils ne doivent pas redevenir la source autoritaire des propriétés propres à une ligne multi-besoins.
- `ResourceRequirement` représente le besoin/budget opérationnel matérialisé. Un besoin issu d'une demande conserve `workforce_request_id` et, lorsque connu, `source_request_line_id`.
- Un besoin `QUICK_SHIFT` / `AD_HOC` peut légitimement ne référencer aucune `WorkforceRequest`.
- `Shift` reste rattaché à un `ResourceRequirement`; un Quick Shift ne crée jamais de fausse demande.

## Demandeur, acteur et contacts

- Le demandeur canonique est référencé par identité stable lorsqu'elle est connue; nom/courriel restent des valeurs d'affichage ou snapshots.
- L'acteur authentifié qui effectue une mutation reste distinct du demandeur métier dans l'audit.
- Un `PROJECT_MANAGER` ne peut pas forcer un autre demandeur par API; la délégation d'un `COORDINATOR` est explicite.
- `AppUser`, `Resource` et `BusinessContact` sont des concepts distincts.
- Les données historiques dont l'identité stable ne peut pas être prouvée restent lisibles sans fabriquer de rapprochement par nom/courriel.

## Périodes, approbation et confirmation

- Le propriétaire métier canonique d'une période est `RequestLine`.
- L'identité logique d'une période est `(request_line_id, period_key)`; son `id` est une version physique persistée.
- Les périodes `CUMULATIVE` sont toutes consommatrices dans l'enveloppe autorisée.
- Un groupe `ALTERNATIVE` ne matérialise qu'une option active; les alternatives non sélectionnées restent néanmoins représentées dans la révision approuvée.
- La demande candidate, la `RequestApprovalRevision` active et le plan opérationnel actif sont trois états distincts.
- Une modification candidate hors enveloppe ne modifie pas le plan actif avant approbation.
- La révision approuvée immuable est la preuve d'autorisation; les `ResourceRequirement` ne suffisent pas à reconstruire toutes les alternatives approuvées.
- `Tentative` / `Confirmée` reste distinct de l'approbation et peut évoluer opérationnellement lorsque l'enveloppe l'autorise.
- Les mutations opérationnelles sensibles utilisent des versions attendues et signalent les conflits.
- Tant que le rebuild reste global, les écritures concurrentes pertinentes du planning participent à la révision globale/CAS définie par ADR-005; l'acquisition se fait avant les lectures décisionnelles et couvre la transaction jusqu'au commit/rollback.

## Capacité, cible et ressources réelles

- `ResourceRequirement.assigned_resource_id` est la cible de génération automatique du reliquat; ce n'est pas la vérité des affectations réelles.
- `Shift.resource_id` est la ressource réellement affectée au quart.
- Un besoin peut avoir des quarts sur plusieurs ressources.
- Un quart verrouillé actif consomme la capacité de son propre `Shift.resource_id`, même sans cible automatique planifiable.
- Créer, modifier ou déplacer un quart ne change pas implicitement la cible automatique.
- La charge ferme et la charge potentielle sont séparées.
- Une demande candidate qui remplace un plan approuvé n'est pas additionnée au plan actif.
- Les groupes alternatifs ne sont jamais sommés naïvement dans les projections de capacité.

## Écritures et audit

- FastAPI reste la frontière de mutation du frontend React.
- Les créations HTTP sensibles utilisent une clé d'idempotence durable lorsqu'elles créent un nouvel objet opérationnel.
- Les commandes composites de planning rejouent le reçu idempotent avant de rejeter une version devenue ancienne et ne font qu'un rebuild par succès neuf.
- Les mutations métier explicites sont auditées avec l'acteur réel disponible.
- Les identités historiques utiles au cutover restent préservées; les nouvelles relations utilisent des IDs stables plutôt que les noms.
- Une exception ou surallocation explicite ne doit jamais réécrire silencieusement l'autorisation approuvée.

## Cutover

Le cutover SQL reste contrôlé : préflight lecture seule, source gelée, migrations explicites, import/réconciliation, puis bascule autoritaire.

Le runtime normal :

- ne lance pas de migration opportuniste sur une base de production explicitement configurée;
- ne retombe pas silencieusement vers Excel;
- conserve le runtime Web/SQL indépendant de NiceGUI/Excel.

Les migrations additives introduites par les évolutions V2, notamment les lignes de demande, révisions approuvées, choix opérationnels et identités canoniques, font désormais partie du schéma à valider sur SQL Server.

La prochaine validation environnementale structurante reste #162 : driver ODBC, migrations et smoke sur le SQL Server cible. Le cutover autoritaire et le retrait du legacy restent suivis dans #208/#336.

## Références

- #13, #162, #208, #288, #328, #329, #331, #332, #336;
- `docs/DEMANDS_V2_ARCHITECTURE.md`;
- ADR-001 à ADR-005.
