# Planification MO — V1.4

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
Bloc de travail à réaliser, assigné ou non
        ↓
AllocationsMO
Heures réellement placées par journée
        ↓
Planning opérationnel
Vue Shifts selon l'horaire et la capacité résiduelle
```

## Planification moyen terme

La page **Planification moyen terme** est une vue Gantt de `Liste_Effort`. Une barre représente une fenêtre de besoin et non un quart continu.

En cliquant sur un effort, la V1.4 permet maintenant :

- de voir toutes les demandes MO liées;
- de modifier directement une demande existante;
- d'ouvrir ses segments;
- de créer une demande supplémentaire en brouillon;
- de créer et soumettre une nouvelle demande.

## Demandes et approbation

Une demande approuvée passe à **En planification** et reçoit automatiquement un segment initial si aucun segment actif n'existe déjà.

Le segment hérite notamment des dates, des heures estimées, de la compétence, de la priorité et du lien vers la planification moyen terme lorsque disponible.

## Segments

`SegmentsMO` représente maintenant le **besoin opérationnel**, pas directement un shift journalier.

Un segment contient notamment :

- la demande et le projet;
- une fenêtre de début et de fin;
- un nombre d'heures prévues;
- une compétence requise;
- une priorité;
- un type de planification `Flexible` ou `Fixe`;
- un technicien facultatif;
- un statut.

### Segment sans technicien

Un segment peut être créé sans technicien. Il passe alors au statut **À assigner** et apparaît dans la zone **Travaux à planifier** du tableau de bord et du Planning opérationnel.

La compétence requise demeure visible afin de faciliter l'assignation future de la bonne ressource.

## Allocations journalières

La nouvelle feuille `AllocationsMO` contient les heures réellement placées par journée. Elle est générée par le moteur de planification à partir des segments.

### Planification fixe

Un segment `Fixe` représente un engagement déjà réservé. Il consomme la capacité avant les segments flexibles.

### Planification flexible

Un segment `Flexible` est étalé sur toute sa fenêtre en fonction de la capacité encore disponible.

Exemple : un besoin flexible de 80 h réparti sur quatre semaines peut produire environ 4 h par jour. Si une journée contient déjà 8 h de travail fixe, le segment flexible reçoit **0 h cette journée** et ses heures sont redistribuées sur les autres journées disposant encore de capacité.

Le moteur tient compte de :

- l'horaire standard;
- les jours fériés;
- les vacances;
- les allocations fixes;
- les segments flexibles déjà placés selon leur priorité.

Si la fenêtre ne contient pas assez de capacité, les heures non placées restent visibles comme **heures restantes** dans la page Segments.

## Planning opérationnel

La vue Shifts est maintenant alimentée par `AllocationsMO` plutôt que directement par la plage complète des segments.

Une carte n'apparaît donc que lorsqu'un nombre d'heures a réellement été alloué à cette ressource pour cette journée.

La zone **Travaux à planifier** affiche les segments sans technicien avec :

- projet;
- description;
- compétence requise;
- nombre d'heures;
- fenêtre de dates;
- action **Planifier**.

## Capacité et tableau de bord

La capacité hebdomadaire est calculée à partir de `Disponibilites` et la charge provient de `AllocationsMO`.

Le tableau de bord présente aussi le nombre de segments **À assigner** et permet de recalculer les allocations.

## Disponibilités

L'écran **Disponibilités** utilise la feuille Excel `Disponibilites`.

Un horaire standard est défini par employé avec les jours de la semaine, l'heure de début, l'heure de fin et une période de validité optionnelle. Les jours fériés et vacances ont priorité sur l'horaire standard.

Un employé sans horaire standard actif n'est pas planifiable et n'apparaît pas parmi les ressources du Planning opérationnel.

## Feuilles applicatives

La connexion crée ou complète au besoin :

- `DemandesMO`;
- `Historique`;
- `Disponibilites`;
- `SegmentsMO`;
- `AllocationsMO`.

`SegmentsMO` reçoit également les colonnes V1.4 `CompetenceRequise`, `TypePlanification` et `Priorite`.

## Configuration locale

Le fichier `app_config.json` est local au poste et ignoré par Git. Un modèle `app_config.example.json` est fourni.

```json
{
  "workbook": "",
  "refresh_seconds": 3,
  "save_on_write": true,
  "host": "127.0.0.1",
  "port": 8080
}
```

Dans **Paramètres**, sélectionne le chemin Windows local de ton classeur `.xlsx` ou `.xlsm`.

## OneDrive

Utilise le chemin **local synchronisé** du fichier plutôt qu'une URL SharePoint, par exemple :

```text
C:\Users\Utilisateur\OneDrive - Entreprise\Planification\PlanificationMoyenLongTerme.xlsx
```

Il est recommandé de configurer le fichier ou son dossier avec **Toujours conserver sur cet appareil**.

## Fichiers ignorés par Git

Le `.gitignore` exclut notamment `app_config.json`, les fichiers `.xlsx/.xlsm`, les fichiers temporaires Excel et l'environnement Python local.

Pour les premiers essais de la V1.4, utilise idéalement une copie du classeur de production puisque la version ajoute `AllocationsMO` et complète `SegmentsMO` avec de nouvelles colonnes.
