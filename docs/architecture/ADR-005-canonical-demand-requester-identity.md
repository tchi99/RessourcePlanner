# ADR-005 — Identité canonique du demandeur distincte de l'acteur

Status: Accepted  
Date: 2026-09-22

## Context

Une `WorkforceRequest` conserve historiquement le demandeur surtout comme
`requester_name`, et l'API Web accepte encore un nom libre. Cette représentation ne
permet pas d'autoriser correctement la délégation : un chargé de projet peut fournir le
nom d'un autre utilisateur, tandis que le nom ou le courriel peuvent changer.

Le demandeur métier doit également rester distinct de l'acteur authentifié qui exécute
la mutation. Un coordonnateur peut créer ou modifier une demande au nom d'un demandeur
autorisé sans que l'audit perde l'identité réelle de l'acteur.

## Decision

L'identité canonique du demandeur d'une `WorkforceRequest` est
`AppUser.id`, persistée dans `WorkforceRequest.requester_user_id`.

`requester_name` reste un snapshot d'affichage et une surface de compatibilité pour
les données historiques. Il ne sert jamais de clé autoritaire pour une nouvelle
délégation. Le champ historique `requester_external_id` n'est pas réinterprété comme
une clé `AppUser`.

Les règles de délégation sont autoritaires côté backend :

- un `PROJECT_MANAGER` crée une demande pour son propre `AppUser.id`; fournir un
  autre identifiant est refusé même par appel API direct;
- un `COORDINATOR` ou `ADMIN` peut choisir explicitement un `AppUser` actif
  admissible;
- est admissible un utilisateur actif possédant la permission
  `manage_demands`;
- les choix de formulaire utilisent l'identifiant stable; le nom n'est qu'un libellé.

L'acteur d'audit reste séparé du demandeur. Les nouvelles entrées
`WorkforceRequestHistory` conservent `actor_user_id = AppUser.id` en plus du snapshot
`actor_name`.

Les demandes historiques dont le demandeur ne peut pas être relié avec certitude
gardent `requester_user_id = NULL` et leur `requester_name` lisible. Aucune migration
ne déduit une identité à partir d'un nom ou d'un courriel. Une modification explicite
future peut canoniser le demandeur avec un identifiant admissible.

## Alternatives considered

### Utiliser le nom ou le courriel comme identité

Rejeté. Ces valeurs sont modifiables et ne constituent pas une clé autoritaire.

### Utiliser `Resource.id` / `employee_external_id`

Rejeté. Le demandeur est une identité applicative et un rôle métier; il n'est pas
nécessairement une ressource planifiable. `AppUser` et `Resource` restent distincts.

### Utiliser `BusinessContact.id`

Rejeté comme identité canonique du demandeur. Un contact métier est utile aux
communications et aux responsabilités opérationnelles, mais l'autorisation de
délégation dépend de l'utilisateur applicatif et de ses rôles.

### Reconstituer les anciennes identités par nom

Rejeté. Une correspondance nominale ne prouve pas l'identité historique.

## Consequences

### Positive

- les appels API directs ne peuvent plus usurper un autre demandeur par texte libre;
- la délégation du coordonnateur est explicite et auditable;
- le demandeur reste distinct de la ressource, des contacts métier et de l'acteur;
- les DTO peuvent transporter une identité stable tout en affichant un snapshot;
- les anciennes demandes restent lisibles sans migration heuristique.

### Trade-offs / negative

- deux colonnes d'identité stables et nullables sont ajoutées;
- les anciennes demandes peuvent rester sans identité canonique jusqu'à une action
  explicite;
- les consommateurs Web doivent utiliser `requester_user_id` au lieu d'un texte libre.

## References

- GitHub Issue #328
- GitHub Issue #55
- GitHub Issue #277
- GitHub Issue #289
- ADR-002
