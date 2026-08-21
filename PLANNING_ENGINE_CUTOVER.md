# Bascule contrôlée du moteur de planification

La configuration locale `app_config.json` accepte maintenant :

```json
"planning_engine_mode": "pure"
```

Valeurs supportées :

- `pure` : **mode recommandé et valeur par défaut des nouvelles installations**. Le moteur pur calcule et persiste directement le plan sans exécuter le moteur historique au préalable.
- `guarded_pure` : mode transitoire conservé temporairement pour diagnostic/rollback. Le moteur historique calcule et persiste d'abord un checkpoint, puis le moteur pur est comparé et n'est écrit que si la comparaison est complète et exacte.
- `legacy` : moteur historique V1.5 raffiné, conservé temporairement comme retour arrière pendant la période de validation du mode `pure` autoritaire.

Une valeur explicitement inconnue retombe sur `legacy` par sécurité. Une configuration absente ou vide utilise `pure`.

## Activation explicite sur une installation existante

La page **Paramètres** affiche maintenant le mode moteur actif et le mode configuré. Une installation existante en `guarded_pure` ou `legacy` n'est jamais migrée silencieusement : utiliser **Activer le moteur pur au prochain redémarrage**, puis redémarrer RessourcePlanner.

La même carte conserve temporairement `guarded_pure` et `legacy` dans une section **Rollback diagnostic temporaire**. Ces choix prennent eux aussi effet au redémarrage suivant.

## Séquence du mode `pure`

1. Lecture des segments, demandes, disponibilités et allocations verrouillées nécessaires au snapshot.
2. Calcul direct avec le moteur pur.
3. Refus du rebuild si un segment actif ne peut pas être interprété par l'adapter pur.
4. Conversion du résultat vers la structure actuelle `AllocationsMO`.
5. Écriture du plan pur.
6. En cas d'erreur pendant l'écriture, restauration du snapshot précédent de `AllocationsMO`.

Le snapshot précédent sert uniquement à récupérer d'une erreur d'écriture. **Le moteur historique n'est pas exécuté dans le chemin `pure`.**

Les allocations manuelles/verrouillées restent des entrées prioritaires du moteur pur, conformément aux règles déjà validées en shadow testing.

## Journal technique de validation terrain

Chaque rebuild direct réellement exécuté en mode `pure` alimente localement `planning_pure_validation.json`. Ce fichier est ignoré par Git et ne contient que des données techniques :

- nombre de cycles `pure` réussis et en erreur;
- nombre de succès consécutifs;
- horodatage du premier/dernier succès et de la dernière erreur;
- durée du dernier cycle;
- nombre de segments et de lignes d'allocation produites;
- type technique de la dernière erreur, le cas échéant.

Aucun nom de projet, technicien, demande, localisation, chemin de classeur ou contenu métier n'est enregistré. La carte **Paramètres** affiche ces compteurs.

Ce journal prouve uniquement que le chemin `pure` autoritaire a réellement tourné. Il ne remplace pas la validation fonctionnelle demandée dans #56 : approbation, réapprobation, annulation, déplacement/verrouillage manuel, fixe/flexible, tentative/confirmé, hors horaire et manque de capacité.

## Mode `guarded_pure` conservé temporairement

Ce mode reste disponible pendant la courte période de validation réelle du moteur pur autoritaire :

1. Rebuild historique et sauvegarde du plan connu.
2. Snapshot du plan historique persistant.
3. Calcul du moteur pur et comparaison shadow.
4. Si la comparaison diffère ou qu'un segment actif n'est pas comparable, conservation immédiate du plan historique.
5. Si la comparaison est exacte, écriture du résultat pur.
6. Nouvelle comparaison après écriture.
7. En cas d'échec, restauration du snapshot historique.

`guarded_pure` effectue volontairement plus de lectures/écritures et ne constitue pas l'architecture de performance cible.

## Retour arrière temporaire

Le moyen recommandé pendant la validation est la section **Rollback diagnostic temporaire** dans Paramètres.

Il reste aussi possible de modifier manuellement `app_config.json` :

```json
"planning_engine_mode": "legacy"
```

ou :

```json
"planning_engine_mode": "guarded_pure"
```

Redémarrer ensuite l'application. Aucun changement de schéma Excel n'est introduit par cette bascule.

## Étape suivante

Après plusieurs cycles réels en `pure` sans retour arrière et après validation des scénarios métier de #56 :

- supprimer le moteur historique de production;
- supprimer `guarded_pure` et la logique de double calcul/checkpoint;
- conserver les scénarios shadow utiles sous forme de tests de non-régression;
- mettre à jour le roadmap maître #55 et fermer #56.
