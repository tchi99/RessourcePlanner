# Parité utile V1 → Web/SQL

> **Statut : audit de transition, mis à jour après la fermeture de #211/#212.**  
> Ce document ne définit pas le roadmap courant; l'ordre de travail est dans #55.

Ce document répond à la question : **quelles capacités V1 doivent encore empêcher le retrait de NiceGUI/Excel?**

## Résumé actuel

Les deux bloqueurs fonctionnels identifiés par l'audit initial sont maintenant fermés :

- ✅ #211 — administration Ressources, compétences et disponibilités;
- ✅ #212 — édition et assignation des Segments / `ResourceRequirement`.

Depuis cet audit, le Web V2 a également livré notamment :

- planning opérationnel React;
- création/édition/verrouillage des quarts;
- Quick Shift;
- WorkPackages / moyen terme;
- demandes multi-lignes (#288);
- périodes et alternatives par ligne (#13 / ADR-002);
- workflow/actions backend autoritaires (#327);
- identité canonique du demandeur (#328);
- projection backend de détail unifiée (#329);
- contacts métier (#289);
- drag-and-drop (#275);
- recommandations et file « à traiter » (#273);
- communications projet (#290).

**Il ne reste donc plus de bloqueur de parité V1 identifié dans #211/#212.**

Les blocages réels du cutover sont maintenant surtout environnementaux et de bascule :

1. #162 — validation SQL Server réelle : ODBC, migrations et smoke;
2. #208 — bascule SQL autoritaire et retrait du runtime V1;
3. #336 — nettoyage post-cutover des artefacts legacy.

#330 améliore actuellement l'ergonomie du détail de demande React, mais ne réintroduit pas un manque de capacité métier exclusif à NiceGUI.

## Matrice actuelle

| Surface / capacité | État Web V2 | Impact cutover |
|---|---|---|
| Planning opérationnel | couvert | aucun bloqueur V1 |
| Quick Shift / ad hoc | couvert | aucun bloqueur V1 |
| Moyen terme / WorkPackages | couvert | aucun bloqueur V1 |
| Demandes / approbations | couvert | #330 consolide l'UX, pas le modèle |
| Périodes / alternatives | couvert par ligne | règles autoritaires dans #13 |
| Segments / besoins | couvert | #212 fermé |
| Ressources / compétences / disponibilités | couvert | #211 fermé |
| Recommandation / « à traiter » | couvert | #273 |
| Drag-and-drop | couvert | #275; enrichissements #332/#333 à venir |
| Communications | couvert localement | validation M365 réelle suivie séparément dans #40 |
| Données Excel génériques | à supprimer | ne pas recréer une grille SQL générique |
| Paramètres OneDrive/xlwings | à supprimer | spécifiques au runtime V1 |
| SQL Server réel | non validé sur cible | **bloque #208** via #162 |
| Retrait NiceGUI/Excel | non terminé | #208 puis #336 |

## Capacités volontairement non reproduites

### Grille Excel générique

Elle ne doit pas être portée vers SQL. Les mutations Web doivent passer par des commandes métier explicites, avec validation et audit.

### Paramètres OneDrive / xlwings

Ils disparaissent avec le runtime Excel autoritaire. Leur absence dans React est une simplification attendue.

### Rebuild comme geste utilisateur principal

Le backend conserve les outils de rebuild/support nécessaires, mais le runtime React doit maintenir le plan via les mutations canoniques plutôt que dépendre d'un bouton de recalcul général.

## Évolutions produit après la parité

Les issues suivantes améliorent le produit sans être des preuves que NiceGUI doit rester en production :

- #330 — détail de demande React unifié;
- #332 — partage et duplication atomiques de quarts;
- #333 — extension de fenêtre et dialogue DnD contextuel;
- #291/#292 — actifs réservables et qualifications;
- #276 — routage d'approbation par tâche;
- #278 — dashboard Coordonnateur.

Ces fonctionnalités doivent respecter les mêmes frontières backend autoritaires; elles ne justifient pas de réinvestir le runtime V1.

## Ordre de cutover

```text
Web V2 fonctionnel / parité utile atteinte
        ↓
#162 validation SQL Server réelle
        ↓
#208 cutover SQL autoritaire
        ↓
#336 nettoyage post-cutover / retrait legacy
```

La cible de déploiement est la VM Ubuntu documentée dans `DEPLOYMENT_UBUNTU_VM.md`; SQL Server reste externe.

## Références

- #55 — roadmap maître;
- #162 — SQL Server réel;
- #208 — cutover autoritaire;
- #211/#212 — anciens bloqueurs de parité, terminés;
- #330 — consolidation UX Demandes;
- #336 — nettoyage post-cutover;
- `docs/DEMANDS_V2_ARCHITECTURE.md`.
