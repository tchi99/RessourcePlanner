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

## Demandes, confirmation et réapprobation

Une demande contient maintenant un niveau de confirmation :

- `Confirmée`;
- `Tentative`.

Les anciennes demandes sans valeur sont traitées comme `Confirmée` afin de préserver le comportement existant.

Une demande tentative peut être approuvée et planifiée normalement, mais ses quarts sont affichés en **jaune pointillé** dans le Planning opérationnel afin de la distinguer visuellement.

Si une demande déjà approuvée est modifiée :

1. elle retourne automatiquement au statut **Soumise**;
2. ses segments et allocations existants restent inchangés pendant l'attente de la nouvelle approbation;
3. une fois la nouvelle version approuvée, les segments sont synchronisés avec les nouvelles dates, heures, compétence, priorité, description et nombre de ressources;
4. les affectations de techniciens déjà faites sont conservées autant que possible.

Si le nombre de ressources diminue lors d'une réapprobation, les segments excédentaires sont annulés; s'il augmente, de nouveaux segments non assignés sont créés.

Les demandes `Soumise` qui chevauchent la semaine affichée sont visibles dans le Planning opérationnel, mais comptent **0 h dans la charge** tant qu'elles ne sont pas approuvées. Une demande soumise et tentative utilise aussi le code visuel jaune.

## Nombre de ressources

`NombreRessources` correspond réellement au nombre de segments à créer.

Exemple : une demande de 80 h pour 2 ressources génère deux segments de 40 h. Si un technicien a été proposé, le premier segment lui est assigné et le second reste **À assigner** afin qu'une deuxième ressource puisse être choisie indépendamment.

## Segments

`SegmentsMO` représente le besoin opérationnel par ressource. Un segment contient notamment :

- la demande et le projet;
- une fenêtre de début et de fin;
- un nombre d'heures prévues;
- une compétence requise;
- une priorité;
- un type de planification `Flexible` ou `Fixe`;
- un technicien facultatif;
- un statut;
- `HorsHoraireAutorise`.

Un segment sans technicien apparaît dans **Travaux à planifier** uniquement lorsque sa fenêtre chevauche la semaine présentement affichée.

### Travail hors horaire au niveau du segment

Le champ `HorsHoraireAutorise` permet d'autoriser le moteur à placer automatiquement le reliquat d'un segment en dehors de l'horaire standard lorsque la capacité normale est insuffisante.

Les vacances restent exclues de cette logique automatique. Les journées sans horaire normal, comme les fins de semaine et jours fériés, sont privilégiées avant les heures supplémentaires de semaine.

Si le segment **n'autorise pas** le hors horaire et que la capacité standard est insuffisante, le moteur affiche des quarts **Hors horaire requis** en orange pointillé. Ces quarts sont des avertissements/propositions et ne sont pas comptés dans la charge réelle tant qu'ils n'ont pas été confirmés.

## Allocations automatiques et verrouillées

`AllocationsMO` contient les heures réellement placées par journée.

La V1.5 ajoute les colonnes :

- `Verrouillee`;
- `HorsHoraire`;
- `Note`.

Le moteur applique l'ordre suivant :

1. allocations manuelles/verrouillées;
2. segments fixes;
3. segments flexibles;
4. hors horaire réel ou requis lorsque la capacité standard ne suffit pas.

Une allocation verrouillée est conservée lors des recalculs. Ses heures sont soustraites du segment puis le moteur redistribue uniquement le reliquat autour de cette décision.

## Quart manuel

Dans **Planning opérationnel**, le bouton **Quart manuel** permet de sélectionner un segment, un technicien, une date et un nombre d'heures.

Un quart manuel est automatiquement verrouillé. Un quart automatique peut aussi être ouvert puis enregistré pour le transformer en décision verrouillée.

Pour un samedi, dimanche, jour férié ou autre journée sans capacité standard, il faut cocher explicitement **Hors horaire** au niveau du quart, sauf si le moteur l'a déjà généré depuis un segment autorisé hors horaire.

Depuis la fenêtre d'un quart, le bouton **Modifier le segment** donne un accès direct au segment parent.

## Code de couleur du Planning opérationnel

- **Bleu** : flexible;
- **Violet** : fixe ou verrouillé manuellement;
- **Jaune pointillé** : demande tentative;
- **Rouge** : journée en surcharge;
- **Orange** : quart hors horaire réellement planifié;
- **Orange pointillé** : capacité insuffisante, quart hors horaire requis mais non confirmé;
- **Gris pointillé** : demande confirmée en attente d'approbation, sans consommation de capacité.

## Capacité et tableau de bord

La capacité hebdomadaire provient de `Disponibilites` et la charge réelle provient des allocations réellement planifiées dans `AllocationsMO`. Les quarts `Hors horaire requis` ne sont pas inclus dans la charge tant qu'ils restent des propositions.

Le dashboard possède un sélecteur de semaine avec précédent / aujourd'hui / suivant. Les KPI, les travaux à assigner et la **charge réelle** sont calculés pour la semaine sélectionnée.

Les heures `HorsHoraire` réellement planifiées sont indiquées séparément de la capacité standard.

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

`DemandesMO` reçoit `Confirmation`. `SegmentsMO` reçoit `HorsHoraireAutorise`. `AllocationsMO` utilise `Verrouillee`, `HorsHoraire` et `Note`.

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

Pour les essais de la V1.5, utilise idéalement une copie du classeur de production puisque la version complète `DemandesMO`, `SegmentsMO` et `AllocationsMO` avec de nouvelles colonnes et modifie le comportement de réapprobation.
