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

## Ressources et compétences — V1.6

La V1.6 ajoute une configuration explicite des ressources dans la feuille `RessourcesMO` et dans la page **Ressources & compétences** de l'application.

Chaque technicien peut recevoir :

- une classe parmi `Programmation`, `Installation`, `Monteur de panneau`, `Dessinateur`, `Gestion de projet`;
- une ou plusieurs compétences provenant de la liste de compétences du classeur;
- une note optionnelle.

Une ressource sans classe reste volontairement dans `Non classé`. Le regroupement du Planning opérationnel n'essaie plus de déduire automatiquement la classe à partir de la description ou de l'équipe du technicien.

Les compétences configurées sont utilisées par **Trouver une ressource**. Une correspondance exacte de compétence est priorisée avant la classe et la capacité disponible. La décision finale demeure manuelle.

Le filtre **Projet** du Planning opérationnel affiche maintenant le numéro et le nom du projet, tout en conservant le numéro comme valeur de filtrage.

## Planification moyen terme

La page **Planification moyen terme** est une vue Gantt de `Liste_Effort`. Une barre représente une fenêtre de besoin et non un quart continu.

En cliquant sur un effort, l'application permet de **modifier directement la ligne correspondante de `Liste_Effort`** et de créer une nouvelle demande MO à partir de cette planification. Les demandes liées restent affichées comme référence, mais leur modification se fait dans **Demandes / approbations**.

La semaine courante est mise en évidence dans le Gantt.

## Demandes, confirmation et réapprobation

Une demande contient un niveau de confirmation `Confirmée` ou `Tentative`.

Une demande tentative peut être approuvée et planifiée normalement, mais ses quarts sont affichés en **jaune pointillé** dans le Planning opérationnel afin de la distinguer visuellement.

Si une demande déjà approuvée est modifiée :

1. elle retourne automatiquement au statut **Soumise**;
2. ses segments et allocations existants restent inchangés pendant l'attente de la nouvelle approbation;
3. une fois la nouvelle version approuvée, les segments sont synchronisés avec les nouvelles dates, heures, compétence, priorité, description et nombre de ressources;
4. les affectations de techniciens déjà faites sont conservées autant que possible.

Les demandes `Soumise` visibles dans le Planning opérationnel comptent 0 h de charge tant qu'elles ne sont pas approuvées.

## Nombre de ressources

`NombreRessources` correspond réellement au nombre de segments à créer.

Exemple : une demande de 80 h pour 2 ressources génère deux segments de 40 h. Si un technicien a été proposé, le premier segment lui est assigné et le second reste **À assigner**.

## Segments

`SegmentsMO` représente le besoin opérationnel par ressource. Un segment contient notamment la demande, le projet, la fenêtre de dates, les heures prévues, la compétence requise, la priorité, le type `Flexible` ou `Fixe`, un technicien facultatif, un statut et `HorsHoraireAutorise`.

Un segment sans technicien apparaît dans **Travaux à planifier** uniquement lorsque sa fenêtre chevauche la semaine présentement affichée.

## Recommandation de ressources — V1.6

Le bouton **Trouver une ressource** analyse toute la fenêtre du segment et classe les candidats selon :

1. la compétence explicitement attribuée au technicien;
2. la classe de ressource;
3. la capacité prudente restante;
4. la charge confirmée et tentative;
5. les heures qui nécessiteraient du hors horaire.

Les recommandations n'affectent jamais automatiquement un technicien. Le bouton **Assigner** applique le choix et relance le moteur d'allocations.

## Planning opérationnel — V1.6

Les ressources sont regroupées dans des sections rétractables selon les cinq classes configurables. À l'intérieur d'une classe, elles sont triées selon leur capacité prudente restante dans la semaine affichée.

Les filtres disponibles comprennent la classe, la ressource, le projet, Confirmée/Tentative et les ressources ayant encore de la capacité. Le filtre Projet affiche `Numéro — Nom du projet`.

## Travail hors horaire

Le champ `HorsHoraireAutorise` permet au moteur de placer automatiquement le reliquat d'un segment en dehors de l'horaire standard lorsque la capacité normale est insuffisante.

Si le segment n'autorise pas le hors horaire et que la capacité standard est insuffisante, le moteur affiche des quarts **Hors horaire requis** en orange pointillé. Ces quarts ne sont pas comptés dans la charge réelle tant qu'ils ne sont pas confirmés.

## Allocations automatiques et verrouillées

`AllocationsMO` contient les heures réellement placées par journée. Les allocations manuelles/verrouillées sont conservées lors des recalculs, puis le moteur redistribue seulement le reliquat.

## Code de couleur du Planning opérationnel

- **Bleu** : flexible;
- **Violet** : fixe ou verrouillé manuellement;
- **Jaune pointillé** : demande tentative;
- **Rouge** : journée en surcharge;
- **Orange** : quart hors horaire réellement planifié;
- **Orange pointillé** : capacité insuffisante, quart hors horaire requis mais non confirmé;
- **Gris pointillé** : demande confirmée en attente d'approbation, sans consommation de capacité.

## Capacité et tableau de bord

Le dashboard possède un sélecteur de semaine. La V1.6 ajoute une synthèse de capacité par classe avec charge confirmée, charge tentative et capacité prudente restante.

## Disponibilités

L'écran **Disponibilités** utilise la feuille Excel `Disponibilites`. Un employé sans horaire standard actif n'est pas planifiable automatiquement.

## Feuilles applicatives

La connexion crée ou complète au besoin :

- `DemandesMO`;
- `Historique`;
- `Disponibilites`;
- `SegmentsMO`;
- `AllocationsMO`;
- `RessourcesMO`.

`RessourcesMO` contient `Technicien`, `Classe`, `Competences` et `Note`.

## Configuration locale

Le fichier `app_config.json` est local au poste et ignoré par Git. Un modèle `app_config.example.json` est fourni.

Dans **Paramètres**, sélectionne le chemin Windows local de ton classeur `.xlsx` ou `.xlsm`. Pour OneDrive, utilise le chemin **local synchronisé** du fichier plutôt qu'une URL SharePoint.
