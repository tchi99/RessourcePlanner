# Planification MO — V1.3

Application locale Python pour piloter un classeur Excel de planification, y compris un classeur stocké dans un dossier **OneDrive synchronisé localement**.

## Architecture V1.3

La V1.3 sépare maintenant les différents niveaux de planification afin de ne plus interpréter une planification moyen terme comme un quart de travail continu.

```text
Liste_Effort
Planification moyen terme / enveloppe de besoin
        ↓
DemandesMO
Besoin de main-d'œuvre / approbation
        ↓
SegmentsMO
Découpage opérationnel du besoin
        ↓
Planning opérationnel
Vue Shifts quotidienne selon l'horaire réel des employés
```

### Planification moyen terme

La page **Planification moyen terme** est une vue Gantt de `Liste_Effort`. Une plage du 3 mars au 8 août signifie qu'un besoin existe dans cette fenêtre; elle ne crée plus automatiquement un quart de travail pour chaque journée de cette période.

En cliquant sur un effort moyen terme, il est possible de créer une demande MO liée. Le lien est conservé dans `DemandesMO.SourceEffortRow`.

La vue affiche également :

- l'effort macro prévu;
- les heures déjà détaillées en segments;
- les heures restant à détailler;
- les demandes MO liées à l'effort.

### Demandes MO

Les demandes conservent le workflow d'approbation existant. Une demande au statut **En planification** peut maintenant être découpée en un ou plusieurs segments plutôt que de créer directement une ligne dans `Liste_Effort`.

### Segments

La nouvelle feuille `SegmentsMO` contient le planning opérationnel réel. Un segment possède notamment :

- une demande MO;
- un projet;
- un technicien;
- une date de début et de fin;
- un nombre d'heures prévues;
- un statut;
- une description;
- un lien optionnel vers une ligne de `Liste_Effort`.

Cela permet par exemple de découper un besoin de 400 h réparti de mars à août en plusieurs blocs de 40 h à des dates différentes.

### Planning opérationnel

La vue **Planning opérationnel** de type Shifts est maintenant alimentée exclusivement par `SegmentsMO`.

Les cartes ne sont affichées que sur les journées où le technicien est disponible selon son horaire. Les week-ends, vacances et jours fériés ne deviennent donc plus artificiellement des quarts de travail simplement parce qu'un segment couvre une longue période.

Les heures d'un segment sont réparties proportionnellement aux heures disponibles dans sa fenêtre. Une surcharge journalière est signalée visuellement.

## Capacité et tableau de bord

La capacité hebdomadaire n'utilise plus `Capacity ÷ 4,33`.

Elle est calculée directement à partir de `Disponibilites` :

- horaire standard du technicien;
- jours réellement travaillés;
- vacances;
- jours fériés.

La charge hebdomadaire provient des segments actifs. Le tableau de bord compare donc maintenant des **heures planifiées opérationnelles** avec des **heures réellement disponibles**.

Un employé sans horaire standard actif :

- n'est pas considéré disponible;
- n'apparaît pas dans le Planning opérationnel;
- n'apparaît pas dans les listes de techniciens planifiables;
- demeure visible dans l'écran Disponibilités afin qu'on puisse lui créer un premier horaire.

## Disponibilités

L'écran **Disponibilités** utilise la feuille Excel `Disponibilites`.

Un horaire standard est défini par employé avec les jours de la semaine, l'heure de début, l'heure de fin et une période de validité optionnelle. Les jours fériés et vacances ont priorité sur l'horaire standard.

Le bouton **Initialiser horaires** crée un horaire standard Lun–Ven 08:00–16:00 uniquement pour les employés auxquels on choisit d'appliquer cette initialisation. Il n'existe plus d'horaire implicite pour un employé non configuré.

## Demandes

- recherche du projet par numéro, nom ou client;
- modification d'une demande existante tant qu'elle n'est pas fermée ou annulée;
- approbation / retour pour correction;
- historique des changements;
- gestion des segments depuis une demande approuvée.

## Feuilles applicatives

La première connexion crée les feuilles nécessaires si elles n'existent pas :

- `DemandesMO`;
- `Historique`;
- `Disponibilites`;
- `SegmentsMO`.

Les feuilles existantes de planification, dont `Liste_Effort`, restent la source de la planification moyen terme.

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

Le `.gitignore` exclut notamment :

- `app_config.json`;
- `*.xlsx` et `*.xlsm`;
- les fichiers temporaires Excel `~$*.xlsx` et `~$*.xlsm`;
- `.venv/` et les fichiers Python temporaires.

Commence idéalement les essais de la V1.3 avec une copie du classeur de production, particulièrement lors de la première création de `SegmentsMO` et de l'ajout de la colonne `SourceEffortRow` à `DemandesMO`.
