# Planification MO — V1.5

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

## Planification moyen terme

La page **Planification moyen terme** est une vue Gantt de `Liste_Effort`. Une barre représente une fenêtre de besoin et non un quart continu.

En cliquant sur un effort, l'application permet de **modifier directement la ligne correspondante de `Liste_Effort`** et de créer une nouvelle demande MO à partir de cette planification. Les demandes liées restent affichées comme référence, mais leur modification se fait dans **Demandes / approbations**.

La V1.5 encadre également la **semaine courante en bleu** dans le Gantt.

## Demandes, modification et réapprobation

Une demande approuvée passe à **En planification** et reçoit des segments opérationnels.

Si une demande déjà approuvée est ensuite modifiée :

- elle retourne automatiquement au statut **Soumise**;
- une nouvelle approbation est requise;
- les informations de la précédente approbation sont réinitialisées;
- les segments et allocations déjà créés ne sont **pas modifiés automatiquement**.

Les segments existants représentent donc la dernière version approuvée jusqu'à ce que la nouvelle demande soit approuvée.

Les demandes `Soumise` qui chevauchent la semaine affichée sont visibles dans le Planning opérationnel sous forme de cartes grises en pointillés. Elles servent à anticiper les besoins, mais comptent **0 h dans la charge** tant qu'elles ne sont pas approuvées.

## Nombre de ressources

`NombreRessources` crée maintenant réellement plusieurs segments lors de la première approbation.

Exemple : une demande de 80 h pour 2 ressources génère deux segments de 40 h. Si un technicien a été proposé, le premier segment lui est assigné et le second reste **À assigner** afin qu'une deuxième ressource puisse être choisie indépendamment.

Si une demande déjà planifiée est réapprouvée avec davantage de ressources, les segments manquants sont ajoutés. Si le nombre de ressources diminue, aucun segment existant n'est supprimé silencieusement : l'écart est inscrit dans l'historique.

## Segments

`SegmentsMO` représente le besoin opérationnel par ressource. Un segment contient notamment :

- la demande et le projet;
- une fenêtre de début et de fin;
- un nombre d'heures prévues;
- une compétence requise;
- une priorité;
- un type de planification `Flexible` ou `Fixe`;
- un technicien facultatif;
- un statut.

Un segment sans technicien apparaît dans **Travaux à planifier** uniquement lorsque sa fenêtre chevauche la semaine présentement affichée.

## Allocations automatiques et verrouillées

`AllocationsMO` contient les heures réellement placées par journée.

La V1.5 ajoute les colonnes :

- `Verrouillee`;
- `HorsHoraire`;
- `Note`.

Le moteur applique l'ordre suivant :

1. allocations manuelles/verrouillées;
2. segments fixes;
3. segments flexibles.

Une allocation verrouillée est conservée lors des recalculs. Ses heures sont soustraites du segment puis le moteur redistribue uniquement le reliquat autour de cette décision.

Ainsi, déplacer manuellement 8 h d'un segment flexible sur une journée précise ne crée pas 8 h supplémentaires : les autres allocations du segment sont recalculées afin de conserver son total prévu.

## Quart manuel et travail hors horaire

Dans **Planning opérationnel**, le bouton **Quart manuel** permet de sélectionner un segment, un technicien, une date et un nombre d'heures.

Un quart manuel est automatiquement verrouillé. Un quart automatique peut aussi être ouvert puis enregistré pour le transformer en décision verrouillée.

Pour un samedi, dimanche, jour férié ou autre journée sans capacité standard, il faut cocher explicitement **Hors horaire**. L'horaire standard du technicien n'est donc pas falsifié pour représenter une exception ponctuelle.

Le quart hors horaire reste inclus dans les heures planifiées et est identifié séparément sur le dashboard.

## Code de couleur du Planning opérationnel

- **Bleu** : flexible;
- **Violet** : fixe ou verrouillé manuellement;
- **Rouge** : journée en surcharge;
- **Orange** : quart explicitement hors horaire;
- **Gris pointillé** : demande en attente d'approbation, sans consommation de capacité.

Cliquer sur une allocation permet de modifier sa journée, ses heures ou son technicien et de la verrouiller. Une allocation verrouillée peut ensuite être remise en mode automatique ou supprimée, après quoi le reliquat est recalculé.

## Capacité et tableau de bord

La capacité hebdomadaire provient de `Disponibilites` et la charge provient de `AllocationsMO`.

Le dashboard possède maintenant un sélecteur de semaine avec précédent / aujourd'hui / suivant. Les KPI, les travaux à assigner et la **charge réelle** sont calculés pour la semaine sélectionnée.

Les heures `HorsHoraire` sont indiquées séparément de la capacité standard.

## Disponibilités

L'écran **Disponibilités** utilise la feuille Excel `Disponibilites`.

Un horaire standard est défini par employé avec les jours de la semaine, l'heure de début, l'heure de fin et une période de validité optionnelle. Les jours fériés et vacances ont priorité sur l'horaire standard.

Un employé sans horaire standard actif n'est pas planifiable automatiquement et n'apparaît pas parmi les ressources normales du Planning opérationnel.

## Feuilles applicatives

La connexion crée ou complète au besoin :

- `DemandesMO`;
- `Historique`;
- `Disponibilites`;
- `SegmentsMO`;
- `AllocationsMO`.

`SegmentsMO` conserve les colonnes `CompetenceRequise`, `TypePlanification` et `Priorite`. `AllocationsMO` reçoit les colonnes V1.5 `Verrouillee`, `HorsHoraire` et `Note`.

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

Pour les premiers essais de la V1.5, utilise idéalement une copie du classeur de production puisque la version complète `AllocationsMO` avec de nouvelles colonnes et change le comportement de réapprobation des demandes.
