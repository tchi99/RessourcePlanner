# Bascule contrôlée du moteur de planification

La configuration locale `app_config.json` accepte maintenant :

```json
"planning_engine_mode": "legacy"
```

Valeurs supportées :

- `legacy` : comportement historique V1.5 raffiné. C'est la valeur par défaut et le fallback pour toute valeur inconnue.
- `guarded_pure` : mode transitoire de validation en production. Le moteur historique calcule et persiste d'abord un checkpoint connu; le moteur pur recalcule ensuite le même plan. Le plan pur n'est persisté que si la comparaison shadow est complète et exacte.

## Séquence de sécurité de `guarded_pure`

1. Rebuild historique et sauvegarde du plan connu.
2. Snapshot du plan historique persistant.
3. Calcul du moteur pur et comparaison shadow.
4. Si la comparaison diffère ou qu'un segment actif n'est pas comparable, conservation immédiate du plan historique.
5. Si la comparaison est exacte, conversion du résultat pur vers la structure actuelle `AllocationsMO` puis écriture.
6. Nouvelle comparaison après écriture.
7. En cas d'échec d'écriture ou de validation, restauration du snapshot historique.

Les messages console de ce mode ne contiennent pas de noms de ressources, projets, chemins de classeur, dates ou identifiants métier.

## Limite temporaire

`guarded_pure` effectue volontairement plus de lectures/écritures qu'un rebuild normal. Ce mode sert à accumuler de la confiance avant la suppression du double calcul. Il ne constitue pas l'architecture de performance cible des issues #17, #18 et #19.

## Retour arrière

Remettre simplement :

```json
"planning_engine_mode": "legacy"
```

puis redémarrer l'application. Aucun changement de schéma Excel n'est introduit par cette bascule.
