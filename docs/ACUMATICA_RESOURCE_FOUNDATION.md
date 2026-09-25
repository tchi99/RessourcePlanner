# Acumatica — fondation locale identité et ressources

Cette tranche prépare la synchronisation des employés et le premier login OIDC sans dépendre du feed réel de l'instance Acumatica.

## Décision de protocole

Les synchronisations métier Acumatica utiliseront **OData**.

La fondation applicative reste volontairement indépendante du protocole grâce aux ports `EmployeeSourcePort` et `ProjectSourcePort`.

L'authentification OIDC des utilisateurs reste un sujet distinct de la lecture OData des données ERP.

## État

Implémenté localement :

- contrat `ExternalEmployeeRecord`;
- `EmployeeSourcePort` et `EmployeeSyncService`;
- repository SQL idempotent vers `ResourceProfile` (`resources`);
- identifiant externe ressource unique lorsqu'il est non nul;
- lien nullable `AppUser.employee_external_id`;
- service explicite `IdentityResourceLinkService`;
- `employee_external_id` disponible dans `AuthPrincipal` et `/api/v1/auth/me`;
- politique de premier login OIDC configurable;
- auto-provisionnement **désactivé par défaut**;
- si activé, seul le rôle `TECHNICIAN` (lecture) peut être attribué automatiquement.

Le contrat Employee/User est maintenant partiellement stabilisé :

- `RP_Employees` est le feed ressources/employés;
- `EmployeID` est sa clé unique et devient l'identité externe canonique de `Resource`;
- `RP_Users` est le feed utilisateurs ERP;
- `UserID` est sa clé unique;
- `RP_Users.EmployeID` référence `RP_Employees.EmployeID`;
- les fixtures anonymisées sont disponibles sous `tests/fixtures/acumatica/`;
- la relation exacte `OIDC (issuer, subject) → RP_Users.UserID` reste à confirmer dans #223/#256.

Le développeur n'a pas besoin d'un accès direct à Acumatica. La règle reste : **PO valide le feed réel → fournit contrat + sample anonymisé → DEV implémente localement → PO exécute le smoke réel**. Voir [ACUMATICA_CONTRACT_WORKFLOW.md](ACUMATICA_CONTRACT_WORKFLOW.md) et [integrations/acumatica/RP_EMPLOYEES_USERS.md](integrations/acumatica/RP_EMPLOYEES_USERS.md).

## Propriété des données

Acumatica possède les attributs organisationnels issus de `RP_Employees` et `RP_Users`. RessourcePlanner doit toutefois séparer explicitement :

- **état source ERP** de l'employé/utilisateur;
- **activation locale RessourcePlanner** décidée par un ADMIN;
- **état effectif utilisable** résultant des deux.

Une nouvelle ressource ou un nouvel utilisateur synchronisé est désactivé localement par défaut, même si l'ERP le déclare actif.

La synchronisation peut mettre à jour les attributs ERP autoritaires, mais elle ne doit pas activer automatiquement une ressource/utilisateur ni écraser silencieusement l'autorisation locale.

RessourcePlanner reste propriétaire de :

- classe de ressource;
- compétences;
- disponibilités et horaires;
- notes;
- ordre d'affichage;
- historique de planning.

Un pull incrémental incomplet ne désactive jamais une ressource absente. Une inactivation doit être reçue explicitement depuis la source.

## Identité ≠ ressource

```text
Acumatica OIDC
      ↓ (issuer, sub)
   AppUser
      │
      │ employee_external_id (nullable)
      ▼
ResourceProfile / resources
      ▲
      │
      └── feed OData Employee/User
```

Le courriel et le nom ne sont jamais des clés autoritaires.

Les cas suivants sont supportés :

- `AppUser` sans ressource : gestionnaire/admin non planifiable;
- ressource sans `AppUser` : sous-traitant ou ressource qui ne se connecte pas;
- compte désactivé avec ressource historique conservée;
- ressource inactive avec compte géré séparément.

## Synchronisation employés

Le port applicatif reste indépendant d'Acumatica :

```text
EmployeeSourcePort
      ↓
EmployeeSyncService
      ↓
EmployeeSyncRepositoryPort
      ↓
SqlEmployeeSyncRepository
      ↓
resources
```

Un adaptateur OData réel remplacera plus tard la source simulée, sans modifier le service métier.

Lorsqu'un `external_id` existe déjà, les champs organisationnels possédés par l'ERP peuvent être mis à jour, mais l'activation locale RessourcePlanner doit être préservée. Le comportement actuel où `ExternalEmployeeRecord.active` écrit directement `Resource.active` doit être revu dans #256 afin de ne plus confondre statut ERP et activation locale.

Les champs de planification locaux restent préservés.

Si une ressource locale non liée possède déjà exactement le même nom qu'un nouvel employé externe, la synchronisation échoue explicitement plutôt que d'adopter la ressource par nom. L'administrateur devra confirmer le bon identifiant externe.

## Auto-provisionnement OIDC

Variable serveur :

```text
RESOURCEPLANNER_OIDC_AUTO_PROVISION=false
```

Valeur par défaut : `false`.

Avec `false`, le comportement existant demeure : une identité OIDC valide mais inconnue reçoit `403 oidc_user_not_registered`.

Avec `true`, une identité OIDC validée cryptographiquement peut créer un `AppUser` au premier login avec :

```text
role = TECHNICIAN
permissions = read
employee_external_id = NULL
```

Un compte local désactivé n'est jamais réactivé automatiquement.

Aucun rôle `ADMIN`, `COORDINATOR`, `PROJECT_MANAGER` ou `MANAGER` ne peut être choisi comme rôle d'auto-provisionnement dans cette fondation.

La politique d'admissibilité pourra être resserrée après #232 lorsque les claims et relations réels de l'instance Acumatica seront connus.

## Schéma SQL

Migration : `0012_acumatica_identity_resources`.

Elle ajoute :

- `app_users.employee_external_id VARCHAR(128) NULL`;
- index unique filtré sur `app_users.employee_external_id IS NOT NULL`;
- index unique filtré sur `resources.external_id IS NOT NULL`.

Les index sont définis explicitement pour SQLite et SQL Server afin de permettre plusieurs valeurs `NULL` tout en interdisant les doublons d'identifiant externe non nul.

## Validation réelle restante

En parallèle du développement local :

- #232 : contrat OData Employee/User + relation identité ↔ employé, produit à partir d'observations réelles mais transmis sous forme désensibilisée;
- #223 : OIDC réel;
- #162 : SQL Server réel.

#207 projets est terminé. Le contract gate Employees/Users a maintenant fixé les feeds et identités principales :

- `RP_Employees.EmployeID` = clé ressource;
- `RP_Users.UserID` = clé utilisateur ERP;
- `RP_Users.EmployeID` = lien vers l'employé.

#256 peut donc commencer les adaptateurs Employee/User et l'administration d'activation locale sans accès ERP développeur. La relation OIDC vers `UserID` demeure un gate séparé.

Le smoke réel final reste une validation environnementale exécutée par une personne autorisée.

Voir aussi [ACUMATICA_ODATA_CONTRACT.md](ACUMATICA_ODATA_CONTRACT.md).
