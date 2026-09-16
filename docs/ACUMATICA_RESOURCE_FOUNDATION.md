# Acumatica — fondation locale identité et ressources

Cette tranche prépare la synchronisation des employés et le premier login OIDC sans dépendre de l'accès réel à l'instance Acumatica.

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

Non implémenté avant la validation #232 :

- endpoint REST Employee/User Acumatica concret;
- noms réels des champs Employee/User;
- claim OIDC contenant un identifiant employé;
- résolution automatique `(issuer, sub) → employee_external_id`;
- Push Notifications employés;
- règles organisationnelles propres à l'instance réelle.

## Propriété des données

Acumatica possédera uniquement les attributs organisationnels retenus dans le contrat réel. La fondation locale limite volontairement la synchronisation à :

- identifiant employé externe;
- nom affiché;
- courriel descriptif;
- actif/inactif.

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
      │
      └─ external_id
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

Un adaptateur Acumatica réel remplacera plus tard la source simulée, sans modifier le service métier.

Lorsqu'un `external_id` existe déjà, seuls `name`, `email` et `active` sont mis à jour. Les champs de planification locaux sont préservés.

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

- #232 : contrat d'intégration réel Acumatica;
- #207 : synchronisation projets réelle;
- #223 : OIDC réel;
- #162 : SQL Server réel.

Une fois #232 suffisamment avancée, il restera principalement à implémenter `AcumaticaEmployeeSource` et le mécanisme de résolution automatique entre l'identité OIDC et l'identifiant employé externe.
