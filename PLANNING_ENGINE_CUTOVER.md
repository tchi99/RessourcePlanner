# Moteur de planification V1.8B — bascule terminée

La période de validation du moteur pur est terminée. Le moteur `pure` est maintenant le **seul moteur de planification de production** de RessourcePlanner.

Les anciens modes `legacy` et `guarded_pure` ne sont plus sélectionnables et ne font plus partie du runtime de production. Une ancienne clé locale `planning_engine_mode` peut encore être présente dans un ancien `app_config.json`; elle est ignorée et sera retirée lors de la prochaine sauvegarde de la configuration.

## Séquence autoritaire

1. Lecture d'un `PlanningSnapshot` unique contenant les entrées nécessaires.
2. Calcul direct avec le moteur pur.
3. Refus du rebuild si un segment actif ne peut pas être interprété par l'adapter pur.
4. Conversion vers la structure courante `AllocationsMO`.
5. Projection des données approuvées nécessaires, notamment la localisation du segment.
6. Écriture du plan.
7. En cas d'échec d'écriture, restauration du snapshot précédent de `AllocationsMO` sans exécuter un moteur historique.

Les allocations manuelles/verrouillées restent des entrées prioritaires du moteur pur.

## Journal technique local

Chaque rebuild direct alimente `planning_pure_validation.json`, fichier local ignoré par Git. Il contient uniquement des métriques techniques : succès/erreurs, succès consécutifs, horodatages, durée, taille du snapshot/résultat et type technique de la dernière erreur.

Aucun projet, technicien, demande, localisation, chemin de classeur ou contenu métier n'est enregistré.

## Historique de la bascule

- V1.8A : validation shadow du moteur pur.
- V1.8B tranche 1 : moteur `pure` direct et snapshot unique.
- V1.8B tranche 2 : utilisation réelle prolongée et validation terrain.
- V1.8B tranche 3 : retrait des modes de rollback `legacy` / `guarded_pure` du runtime de production.

Les anciens modules V1.x encore présents dans le dépôt peuvent toujours contenir du code historique pour des besoins de compatibilité UI/persistance. Ils ne constituent plus un moteur de planification sélectionnable. Leur extraction physique se poursuit dans le chantier architectural #15.
