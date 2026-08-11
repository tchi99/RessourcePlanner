# Planification MO — V1.6

Application locale Python pour piloter un classeur Excel de planification, y compris un classeur stocké dans un dossier **OneDrive synchronisé localement**.

## Architecture

```text
Liste_Effort
Planification moyen terme / enveloppe de besoin
        ↓
DemandesMO
Besoin de main-d'œuvre / approbation
        ↓
SegmentsMO
Bloc de travail par ressource, assigné ou non
        ↓
AllocationsMO
Heures réellement placées par journée
        ↓
Planning opérationnel
Vue Shifts selon l'horaire, les décisions verrouillées et la capacité résiduelle
```

## V1.6 — classes de ressources et aide à l'affectation

La V1.6 organise le Planning opérationnel selon les cinq classes utilisées par le classeur :

- **Programmation**;
- **Installation**;
- **Monteur de panneau**;
- **Dessinateur**;
- **Gestion de projet**.

Chaque classe est affichée dans un groupe rétractable. À l'intérieur du groupe, les ressources sont triées du plus grand nombre d'heures disponibles au plus petit pour la semaine affichée.

La classe est déterminée à partir des informations de `Configuration des listes`. La description/équipe associée à la ressource est priorisée, avec prise en charge d'une colonne explicite de classe lorsqu'elle existe. Une ressource qui ne peut pas être associée aux cinq classes demeure visible sous **Non classé**.

### Filtres du Planning opérationnel

La V1.6 ajoute des filtres pour :

- la classe;
- la ressource;
- le projet;
- le niveau `Confirmée` / `Tentative`;
- les ressources ayant encore de la capacité prudente.

La capacité prudente correspond à la capacité standard moins la charge confirmée et la charge tentative déjà planifiée.

## Travaux à planifier et recommandations

Un segment non assigné de la semaine affichée possède maintenant l'action **Trouver une ressource**.

Le moteur de recommandation examine toute la fenêtre du segment, pas seulement la semaine visible. Il tient compte de :

- la classe suggérée à partir de la compétence et du champ d'expertise;
- la capacité standard totale de la ressource dans la fenêtre;
- la charge confirmée déjà planifiée;
- la charge tentative déjà planifiée;
- les heures qui devraient être faites hors horaire si la capacité prudente est insuffisante.

Les candidats compatibles avec la classe requise et capables d'absorber le travail dans leur capacité prudente sont classés en premier. L'utilisateur conserve toujours la décision finale avec le bouton **Assigner**.

Une fois la ressource choisie, le segment passe à `Planifié` et le moteur V1.5 recalcule les allocations, y compris les quarts flexibles, fixes, hors horaire et les besoins hors horaire requis.

## Capacité par classe au Dashboard

Le Dashboard conserve son sélecteur de semaine et reçoit une synthèse supplémentaire par classe :

```text
Programmation      72 h confirmées · 16 h tentatives · 40 h libres / 128 h
Installation       48 h confirmées ·  0 h tentatives · 32 h libres / 80 h
...
```

Cette vue permet d'évaluer rapidement la capacité globale avant de sélectionner une personne précise.

## Planification moyen terme

La page **Planification moyen terme** est une vue Gantt de `Liste_Effort`. Une barre représente une fenêtre de besoin et non un quart continu.

En cliquant sur un effort, l'application permet de **modifier directement la ligne correspondante de `Liste_Effort`** et de créer une nouvelle demande MO à partir de cette planification. La semaine courante demeure mise en évidence.

## Demandes, confirmation et réapprobation

Une demande possède un niveau `Confirmée` ou `Tentative`. Une demande tentative peut être approuvée et planifiée normalement, mais ses quarts demeurent visuellement distincts dans le Planning opérationnel.

Si une demande déjà approuvée est modifiée :

1. elle retourne au statut **Soumise**;
2. ses segments et allocations restent inchangés pendant l'attente;
3. lors de la nouvelle approbation, les segments sont synchronisés avec la nouvelle version approuvée;
4. les affectations existantes sont conservées autant que possible.

Les demandes `Soumise` qui chevauchent la semaine affichée restent visibles dans le Planning opérationnel, mais comptent **0 h dans la charge** tant qu'elles ne sont pas approuvées.

## Segments et hors horaire

`SegmentsMO` représente le besoin opérationnel par ressource. Un segment possède notamment une compétence requise, une priorité, un type `Flexible` ou `Fixe`, un technicien facultatif et `HorsHoraireAutorise`.

Si la capacité standard est insuffisante :

- avec `HorsHoraireAutorise = Oui`, le moteur peut générer de vraies allocations hors horaire;
- sinon, il affiche des quarts **Hors horaire requis** qui restent des propositions et ne sont pas comptés dans la charge réelle.

Les vacances restent exclues de cette logique automatique.

## Allocations et code de couleur

`AllocationsMO` contient les heures réellement placées par journée. Les allocations verrouillées sont conservées lors des recalculs et le reliquat est redistribué autour de ces décisions.

Code visuel :

- **Bleu** : flexible;
- **Violet** : fixe ou verrouillé;
- **Jaune pointillé** : tentative;
- **Rouge** : surcharge;
- **Orange** : hors horaire planifié;
- **Orange pointillé** : hors horaire requis;
- **Gris pointillé** : attente d'approbation, 0 h de charge.

Depuis un quart, **Modifier le segment** donne accès au segment parent.

## Disponibilités

L'écran **Disponibilités** utilise `Disponibilites`. Un horaire standard explicite est requis pour qu'une ressource soit planifiable. Les jours fériés et vacances ont priorité sur l'horaire standard.

## Feuilles applicatives

La connexion crée ou complète au besoin :

- `DemandesMO`;
- `Historique`;
- `Disponibilites`;
- `SegmentsMO`;
- `AllocationsMO`.

## Configuration locale

Le fichier `app_config.json` est local au poste et ignoré par Git. Un modèle `app_config.example.json` est fourni. Utilise le chemin Windows **local synchronisé** du classeur OneDrive/SharePoint plutôt qu'une URL HTTPS.

Pour les essais de la V1.6, utilise idéalement une copie du classeur de production. La V1.6 ne crée pas de nouvelle feuille, mais elle dépend de la qualité des informations de classe présentes dans `Configuration des listes`.
