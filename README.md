# Planification MO — V1.8

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

## Moteur de planification — V1.8B

Le moteur `pure` est maintenant le **seul moteur de planification de production**. Les anciens modes `legacy` et `guarded_pure` ont été retirés du runtime après une période prolongée de validation terrain.

Le moteur construit un `PlanningSnapshot` unique, calcule le plan en Python pur puis persiste le résultat dans `AllocationsMO`. En cas d'échec d'écriture, le snapshot précédent des allocations est restauré sans recalcul historique.

La clé locale `planning_engine_mode` n'est plus utilisée. Si elle existe encore dans un ancien `app_config.json`, elle est ignorée et retirée lors de la prochaine sauvegarde de la configuration.

## Planification moyen terme enrichie — V1.8

La V1.8 stabilise d'abord le lien entre la planification macro et le détail opérationnel :

- chaque ligne de `Liste_Effort` reçoit un identifiant stable `IDEffort`;
- `DemandesMO` et `SegmentsMO` reçoivent `SourceEffortID`;
- les anciens liens `SourceEffortRow` sont migrés automatiquement vers le nouvel identifiant stable;
- `SourceEffortRow` est conservé temporairement pour compatibilité, mais n'est plus la référence principale;
- une nouvelle ligne ajoutée directement dans `Liste_Effort` reçoit automatiquement un `IDEffort` lors de sa prochaine lecture par l'application.

La vue **Planification moyen terme** affiche maintenant un mini-Gantt détaillé sur 16 semaines :

- l'enveloppe macro de `Liste_Effort` reste visible en arrière-plan;
- les segments liés sont superposés dans la même ligne;
- les segments fixes, flexibles, tentatifs et non assignés sont visuellement distingués;
- un segment qui dépasse l'enveloppe macro reçoit un avertissement et un contour rouge;
- les heures macro sont comparées aux heures segmentées afin de voir immédiatement le reste à détailler ou un dépassement;
- cliquer sur l'enveloppe ouvre l'effort macro; cliquer sur un segment ouvre directement le segment.

Des filtres sont disponibles par projet, chargé de projet, statut, classe de ressource, technicien et compétence. La vue peut être regroupée par **chargé de projet**.

Une heatmap de capacité par classe compare, semaine par semaine, la charge détaillée confirmée + tentative avec la capacité standard des ressources. Cette capacité reste globale même lorsqu'un projet particulier est filtré afin de conserver le contexte réel de disponibilité.

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

### Ordre manuel propre à chaque utilisateur

À partir de la V1.7.1, le tri **Ordre manuel** n'est plus une donnée partagée du classeur Excel. Il est enregistré dans `user_preferences.json`, un fichier local ignoré par Git.

Chaque poste peut donc organiser les techniciens différemment tout en travaillant avec le même classeur partagé. Le fichier local sépare aussi les préférences par classeur à l'aide d'une empreinte du chemin; le chemin Windows réel n'est pas stocké dans ce fichier.

Lors de la première utilisation après mise à niveau, un ancien ordre V1.7 présent dans `RessourcesMO` peut être copié une seule fois vers les préférences locales afin de conserver l'ordre existant. Les modifications suivantes ne réécrivent plus l'ordre manuel dans Excel.

## Performance Excel — V1.7.1

La V1.7.1 réduit le coût des échanges avec Excel tout en conservant le classeur comme source de vérité :

- plusieurs appels `save()` d'une même action sont regroupés derrière une seule sauvegarde réelle;
- l'affichage, les événements et le recalcul Excel sont suspendus temporairement pendant certains lots d'écritures lorsque possible;
- les lectures répétitives de `Disponibilites` sont mises en cache très brièvement pendant le rendu/calcul;
- les initialisations de structure déjà effectuées ne sont pas rejouées inutilement à chaque lecture;
- la création/modification d'une demande et son historique sont regroupés;
- l'initialisation de plusieurs horaires standards et certaines opérations composées utilisent également le mode batch;
- des métriques locales indiquent le temps total et le temps consacré à la sauvegarde Excel pour les opérations lentes.

## Ressources et compétences

`RessourcesMO` contient les données partagées de ressource : `Technicien`, `Classe`, `Competences`, `Note` et, pour compatibilité avec la V1.7, éventuellement l'ancienne colonne `Ordre`.

Les classes disponibles sont : `Programmation`, `Installation`, `Monteur de panneau`, `Dessinateur`, `Gestion de projet`.

Une nouvelle ressource peut être créée directement dans **Ressources & compétences**. Elle reste non planifiable tant qu'un horaire standard actif n'a pas été créé dans **Disponibilités**.

Une ressource sans classe reste dans `Non classé`. Les compétences configurées sont utilisées par **Trouver une ressource** : une correspondance exacte de compétence est priorisée avant la classe et la capacité disponible. La décision finale demeure manuelle.

## Demandes, confirmation et réapprobation

Une demande contient un niveau de confirmation `Confirmée` ou `Tentative`.

Une demande tentative peut être approuvée et planifiée normalement, mais ses quarts sont affichés en **jaune pointillé** dans le Planning opérationnel afin de la distinguer visuellement.

Si une demande déjà approuvée est modifiée :

1. elle retourne automatiquement au statut **Soumise**;
2. ses segments et allocations existants restent inchangés pendant l'attente de la nouvelle approbation;
3. une fois la nouvelle version approuvée, les segments sont synchronisés avec les nouvelles dates, heures, compétence, priorité, description, localisation et nombre de ressources;
4. les affectations de techniciens déjà faites sont conservées autant que possible.

Les demandes `Soumise` visibles dans le Planning opérationnel comptent 0 h de charge tant qu'elles ne sont pas approuvées.

## Nombre de ressources

`NombreRessources` correspond réellement au nombre de segments à créer.

Exemple : une demande de 80 h pour 2 ressources génère deux segments de 40 h. Si un technicien a été proposé, le premier segment lui est assigné et le second reste **À assigner**.

## Segments

`SegmentsMO` représente le besoin opérationnel par ressource. Un segment contient notamment la demande, le projet, la fenêtre de dates, les heures prévues, la compétence requise, la priorité, le type `Flexible` ou `Fixe`, un technicien facultatif, un statut, `HorsHoraireAutorise`, `SiteClient` et `Lieu`.

Un segment sans technicien apparaît dans **Travaux à planifier** uniquement lorsque sa fenêtre chevauche la semaine présentement affichée.

## Recommandation de ressources

Le bouton **Trouver une ressource** analyse toute la fenêtre du segment et classe les candidats selon :

1. la compétence explicitement attribuée au technicien;
2. la classe de ressource;
3. la capacité restante après travaux confirmés et tentatifs;
4. les heures qui devraient être faites hors horaire.

L'application suggère une ressource, mais ne fait aucune affectation automatique sans action de l'utilisateur.

## Allocations et hors horaire

`AllocationsMO` représente les heures réellement placées par journée. Chaque allocation porte aussi la localisation approuvée (`SiteClient` et `Lieu`) projetée depuis son segment.

Une allocation manuelle ou déplacée devient verrouillée et consomme la capacité avant les allocations flexibles. Les allocations non verrouillées sont recalculées autour des décisions manuelles.

Un segment peut autoriser explicitement le travail hors horaire. Si sa fenêtre ne contient pas assez de capacité normale :

- si le hors horaire est autorisé, les heures supplémentaires sont placées comme allocations hors horaire;
- sinon, le Planning opérationnel affiche des quarts **Hors horaire requis** qui signalent le manque sans le compter dans la charge réelle.

Les vacances restent exclues des propositions automatiques de hors horaire.


## Import des projets ERP sous Docker

L'importateur Excel est disponible comme service Docker one-shot `import-projects`. Il utilise le même volume `resourceplanner-data` que FastAPI, donc les projets importés deviennent immédiatement disponibles dans la base SQLite du stack Docker.

Déposer l'export ERP dans le dossier `imports/`, puis prévisualiser l'import sans modifier la base :

```bash
docker compose run --rm import-projects /imports/Projets.xlsx
```

Pour appliquer les changements :

```bash
docker compose run --rm import-projects /imports/Projets.xlsx --apply
```

Le service dépend de `migrate`, ce qui garantit que les migrations Alembic sont appliquées avant l'import. Il appartient au profil `tools` et ne se lance donc pas pendant un simple `docker compose up`.

Le catalogue de tâches ERP utilise le service one-shot `import-tasks` et accepte XLSX/XLSM ou CSV :

```bash
docker compose run --rm import-tasks "/imports/Tâches de projet.xlsx"
docker compose run --rm import-tasks "/imports/Tâches de projet.xlsx" --apply
```

La clé autoritaire d'une tâche est le couple `(ID projet, ID tâche)`. Le détail du mapping réel,
des statuts et de l'API de recherche est documenté dans `docs/ERP_TASK_CATALOG.md`.

Un autre dossier hôte peut être utilisé en définissant `RESOURCEPLANNER_IMPORTS_PATH`. Les exports restent montés en lecture seule dans le conteneur.

## Source Excel et fichiers locaux

Le chemin du classeur est configuré localement dans `app_config.json`, fichier ignoré par Git. Les fichiers `.xlsx` et `.xlsm` sont également ignorés par le dépôt.

`user_preferences.json` est lui aussi local et ignoré par Git. Il contient les préférences propres au poste, notamment l'ordre manuel des ressources. Il peut contenir des noms de ressources et ne doit donc pas être partagé ou versionné.

`planning_pure_validation.json` est un journal technique local ignoré par Git. Il contient uniquement des compteurs et métriques du moteur pur, sans données métier.

Le classeur peut être stocké dans un dossier OneDrive synchronisé localement. L'application utilise le chemin Windows local et communique avec Excel via `xlwings`.
