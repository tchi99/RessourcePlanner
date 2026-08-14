# Audit d'optimisation et d'architecture — post-V1.8

Date de l'audit : 2026-08-14

## Résumé

La V1.8 est fonctionnelle et les optimisations V1.7.1 ont corrigé le problème le plus visible : trop de sauvegardes Excel pour une seule action utilisateur. Le prochain risque n'est plus une sauvegarde isolée, mais la **croissance de la complexité et du volume de travail par action**.

Le code applicatif contient maintenant environ 30 modules Python dans `app/` pour un peu plus de 600 Ko de source. Plusieurs gros modules dépassent 30–60 Ko (`ui.py`, `v13.py`, `v15_refinements.py`, `v17.py`, etc.). La structure actuelle par numéro de version et les wrappers successifs ont été efficace pour prototyper rapidement, mais elle ne doit pas devenir l'architecture permanente.

Recommandation globale : faire une phase de **stabilisation/refactorisation sans ajout fonctionnel majeur** avant la prochaine grosse extension.

## Ce qui est déjà bien en place

- `batch_update` réduit fortement les sauvegardes physiques Excel;
- suspension temporaire du recalcul/événements Excel pendant les batches;
- cache court de disponibilité et invalidation après écritures;
- écritures bulk pour certaines opérations;
- `IDEffort`/`SourceEffortID` stabilisent le lien macro → détail;
- confidentialité : classeurs/config locale ignorés, privacy scan CI;
- tests de démarrage Windows du package;
- EXE autonome;
- préférences d'ordre manuel locales;
- séparation conceptuelle demande → segment → allocation déjà utile pour l'évolution future.

## P0 — Architecture runtime

Issue : #15

`main.py` installe successivement les fonctionnalités/correctifs V1.3 à V1.8. Plusieurs installateurs remplacent dynamiquement des méthodes de `PlannerUI`, `ExcelRepository` ou des fonctions de modules précédents. Certains correctifs remplacent temporairement `ui.select` ou `ui.scroll_area`.

Risques :
- comportement dépendant de l'ordre d'installation;
- difficile de savoir quelle implémentation est active à la fin;
- wrappers imbriqués lors d'une approbation/modification;
- risques futurs avec plusieurs sessions UI;
- dette croissante à chaque nouvelle version.

Action : refactoriser progressivement vers des modules organisés par domaine et une composition explicite, sans big-bang.

## P0 — Tests et reproductibilité

Issue : #16

La CI compile les fichiers Python et vérifie que l'application démarre, mais le moteur de planification n'a pas encore de couverture automatisée suffisante. Les versions NiceGUI/xlwings restent définies par de larges plages.

Action : extraire les règles métier pures, ajouter des tests synthétiques, puis figer les versions réellement validées pour les releases. Cette étape doit accompagner la refactorisation #15 afin d'éviter une refactorisation « à l'aveugle ».

## P1 — Accès Excel : snapshot/read model

Issue : #17

Le repository et les couches V1.x peuvent relire plusieurs fois les mêmes feuilles pendant un rendu ou une action. `used_range`, headers, profils, demandes, segments et allocations sont souvent récupérés par des helpers indépendants.

Action : une opération de lecture devrait créer un snapshot cohérent avec une lecture bulk par feuille. Le reste du calcul devrait se faire en mémoire. Les migrations de schéma doivent être séparées des simples lectures.

## P1 — Rebuild des allocations

Issue : #18

Le moteur recalcule actuellement tous les segments actifs et `_write_allocations` efface/réécrit l'ensemble de `AllocationsMO`. C'est robuste et simple, mais le coût grandira avec le volume.

Action : d'abord benchmarker. Ensuite introduire un recalcul par portée impactée lorsque possible, avec fallback global et tests d'équivalence.

## P1 — Réactivité de l'interface

Issue : #19

Même lorsque les sauvegardes sont regroupées, xlwings/COM et les recalculs restent bloquants. Une action de plusieurs secondes peut immobiliser la boucle UI.

Action : créer une file Excel sérialisée possédant l'accès COM. L'UI soumet les opérations et reste réactive, sans autoriser plusieurs writers simultanés.

## P1 — Identité des ressources et classification des compétences

Issue : #20

Les noms de techniciens servent encore souvent d'identité technique. Le mapping compétence → classe utilise encore partiellement des heuristiques textuelles; le cas `Installation automatisation` a déjà montré une ambiguïté.

Action : IDs stables et mapping explicite dans les données. À préparer avant d'étendre le modèle à d'autres types de ressources.

## P1 — Connexion Excel/OneDrive

Issue : #21

`ExcelRepository.connect()` compare le chemin configuré à `Path(book.fullname).resolve()`. Un classeur ouvert via OneDrive/SharePoint peut exposer un `fullname` distant qui ne correspond pas correctement au chemin local synchronisé.

Action : stratégie de correspondance robuste et tests Windows pour fichier fermé/déjà ouvert/OneDrive.

## P2 — Observabilité/performance

Issue : #22

Les métriques V1.7.1 sont une bonne base mais elles ne séparent pas encore systématiquement lecture, calcul, écriture, sauvegarde et rendu.

Action : instrumentation locale structurée et benchmarks synthétiques permettant de détecter une régression avant release.

## Release signing

Issue : #23

Le pipeline de release était encore figé sur V1.7.2 et publiait un EXE non signé. La branche `chore/release-signing-and-audit` le remplace par :
- builds PR non signés;
- builds manuels signés pour validation;
- releases par tags `v*`;
- authentification GitHub OIDC → Azure;
- Azure Artifact Signing;
- validation Authenticode obligatoire;
- checksum après signature.

La partie code est prête, mais l'activation réelle dépend de la création des ressources Azure et de la validation d'identité. Voir `CODE_SIGNING.md`.

## Roadmap proposée après V1.8

### Phase A — Infrastructure release

1. terminer #23 (Artifact Signing Azure + test réel d'un EXE signé);
2. fusionner le pipeline de release signé;
3. publier la prochaine release uniquement après validation Authenticode.

### Phase B — Stabilisation interne

1. #16 tests et dépendances;
2. #15 refactorisation progressive de l'architecture;
3. #17 snapshot Excel et migrations;
4. #21 connexion OneDrive/classeur ouvert.

### Phase C — Performance à l'échelle

1. #22 benchmarks/observabilité;
2. #18 rebuild incrémental des allocations;
3. #19 worker/file Excel sérialisée et UI non bloquante.

### Phase D — Modèle de données évolutif

1. #20 IDs stables et mapping explicite des compétences/classes;
2. #13 périodes de demande avec confirmation distincte;
3. #14 profils de charge des segments;
4. reprendre ensuite les évolutions fonctionnelles plus importantes.

## Conclusion

Il n'est pas nécessaire de réécrire l'application. Le meilleur rendement est une refactorisation **incrémentale**, protégée par des tests, qui transforme progressivement les couches historiques en services explicites. Les fonctionnalités actuelles peuvent rester identiques pendant cette phase.
