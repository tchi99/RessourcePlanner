# Planification MO — V1.7

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

## Planning opérationnel interactif — V1.7

La V1.7 rend le Planning opérationnel manipulable directement :

- glisser-déposer un quart sur une autre journée pour le déplacer et le verrouiller;
- déplacer vers une autre ressource avec choix entre réaffecter le segment complet ou fractionner uniquement les heures du quart;
- glisser un travail non assigné sur une ressource;
- créer rapidement un quart depuis le bouton `+` d'une cellule Ressource × Jour;
- ouvrir les demandes non approuvées directement depuis les cartes du planning ou la section d'attente d'approbation;
- réduire la section **En attente d'approbation**;
- conserver la position de la page et le défilement du calendrier après les rafraîchissements;
- trier les ressources à l'intérieur de chaque classe par disponibilité, disponibilité inverse, ordre alphabétique A→Z / Z→A ou ordre manuel.

Le tri **Ordre manuel** est enregistré dans la colonne `Ordre` de `RessourcesMO`. La page **Ressources & compétences** contient un bouton **Ordre manuel** pour modifier rapidement les positions. Les valeurs peuvent être espacées (10, 20, 30...) pour faciliter l'insertion future d'une ressource entre deux autres.

Le recalcul du moteur reste global dans cette première version de la V1.7 afin de privilégier la cohérence du classeur Excel. Une optimisation par segment ou ressource pourra être faite après validation des interactions.

## Ressources et compétences

`RessourcesMO` contient maintenant :

- `Technicien`;
- `Classe`;
- `Competences`;
- `Note`;
- `Ordre` pour le tri manuel.

Les classes disponibles sont : `Programmation`, `Installation`, `Monteur de panneau`, `Dessinateur`, `Gestion de projet`.

Une nouvelle ressource peut être créée directement dans **Ressources & compétences**. Elle reste non planifiable tant qu'un horaire standard actif n'a pas été créé dans **Disponibilités**.

Une ressource sans classe reste dans `Non classé`. Les compétences configurées sont utilisées par **Trouver une ressource** : une correspondance exacte de compétence est priorisée avant la classe et la capacité disponible. La décision finale demeure manuelle.

Le filtre **Projet** du Planning opérationnel affiche le numéro et le nom du projet, tout en conservant le numéro comme valeur de filtrage.

## Planification moyen terme

La page **Planification moyen terme** est une vue Gantt de `Liste_Effort`. Une barre représente une fenêtre de besoin et non un quart continu.

En cliquant sur un effort, l'application permet de **modifier directement la ligne correspondante de `Liste_Effort`** et de créer une nouvelle demande MO à partir de cette planification. Les demandes liées restent affichées comme référence, mais leur modification se fait dans **Demandes / approbations**.

La semaine courante est mise en évidence dans le Gantt.

Une évolution prévue du roadmap ajoutera les segments liés sous forme de mini-Gantt à l'intérieur de chaque ligne de planification moyen terme afin de comparer visuellement l'enveloppe macro et la planification détaillée.

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

## Recommandation de ressources

Le bouton **Trouver une ressource** analyse toute la fenêtre du segment et classe les candidats selon :

1. la compétence explicitement attribuée au technicien;
2. la classe de ressource;
3. la capacité restante après travaux confirmés et tentatifs;
4. les heures qui devraient être faites hors horaire.

L'application suggère une ressource, mais ne fait aucune affectation automatique sans action de l'utilisateur.

## Allocations et hors horaire

`AllocationsMO` représente les heures réellement placées par journée.

Une allocation manuelle ou déplacée devient verrouillée et consomme la capacité avant les allocations flexibles. Les allocations non verrouillées sont recalculées autour des décisions manuelles.

Un segment peut autoriser explicitement le travail hors horaire. Si sa fenêtre ne contient pas assez de capacité normale :

- si le hors horaire est autorisé, les heures supplémentaires sont placées comme allocations hors horaire;
- sinon, le Planning opérationnel affiche des quarts **Hors horaire requis** qui signalent le manque sans le compter dans la charge réelle.

Les vacances restent exclues des propositions automatiques de hors horaire.

## Source Excel

Le chemin du classeur est configuré localement dans `app_config.json`, fichier ignoré par Git. Les fichiers `.xlsx` et `.xlsm` sont également ignorés par le dépôt.

Le classeur peut être stocké dans un dossier OneDrive synchronisé localement. L'application utilise le chemin Windows local et communique avec Excel via `xlwings`.
