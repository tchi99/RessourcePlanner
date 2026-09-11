# Pré-cutover — invariants du modèle opérationnel

Ce document fixe les invariants fonctionnels qui doivent rester vrais pendant le passage Excel/NiceGUI vers SQL/FastAPI/React.

## Propriété des données

- `Project` porte le responsable de projet. La demande, le besoin et le quart ne dupliquent pas cette valeur comme source autoritaire.
- `WorkforceRequest` porte le demandeur opérationnel et peut référencer directement un `WorkPackage`.
- `ResourceRequirement` représente le besoin opérationnel. Un besoin issu d'une demande garde `workforce_request_id`; un besoin `QUICK_SHIFT`/`AD_HOC` peut légitimement avoir cette FK à `NULL`.
- Un besoin ad hoc conserve son auteur dans `created_by_external_id` / `created_by_name`; l'auteur vient du contexte d'identité serveur, pas du corps HTTP.
- `Shift` reste rattaché à un `ResourceRequirement`; un Quick Shift ne crée jamais de fausse demande.

## Alternatives, approbation et confirmation

- Les périodes `CUMULATIVE` sont toutes consommatrices une fois l'enveloppe approuvée.
- Un groupe `ALTERNATIVE` ne matérialise qu'une seule option sélectionnée; un groupe non résolu ne matérialise aucun besoin opérationnel.
- Modifier la définition de l'enveloppe après approbation exige une nouvelle approbation et conserve le plan approuvé en place jusque-là.
- Changer seulement la sélection d'une alternative à l'intérieur de l'enveloppe approuvée ne constitue pas une nouvelle enveloppe.
- `Tentative` / `Confirmée` est distinct de l'approbation et peut être hérité ou surchargé aux niveaux besoin et quart.

## Capacité et ressources

- Le planning hebdomadaire n'affiche comme planifiables que les ressources dont l'horaire standard chevauche la semaine affichée; l'historique demeure conservé.
- La charge ferme et la charge potentielle sont séparées.
- Une demande soumise qui modifie un plan approuvé est une proposition de remplacement et n'est pas additionnée au plan actuel.
- La capacité moyen terme expose charge planifiée et charge macro projetée séparément; elles ne sont pas additionnées naïvement.
- Les groupes de périodes alternatives ne sont jamais sommés entre eux dans la projection de capacité.

## Écritures et audit

- Les actions NiceGUI sensibles sont protégées contre les doubles clics en vol.
- Les créations HTTP sensibles utilisent une clé d'idempotence durable côté SQL.
- Les identités métier historiques (`NoDemande`, `IDEffort`, `IDSegment`, `IDAllocation`) sont préservées pendant le cutover.
- Le cutover préserve aussi `CreePar` des segments comme auteur opérationnel SQL lorsqu'il existe.

## Cutover

Le cutover SQL reste one-shot et transactionnel : préflight lecture seule, classeur gelé, migrations explicites, import, réconciliation puis commit. Le runtime normal ne lance aucune migration opportuniste et ne retombe pas silencieusement vers Excel.

Après fusion de la tranche qui ajoute `created_by_name`, toute nouvelle modification de schéma métier doit être traitée explicitement comme une rupture du gel pré-cutover. La prochaine validation attendue est l'exécution réelle de la chaîne Alembic/runtime sur l'environnement SQL Server cible (#162).
