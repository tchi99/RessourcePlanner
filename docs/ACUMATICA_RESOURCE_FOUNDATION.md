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

Non implémenté avant la validation #232 :

- feed/vue OData Employee/User réel;
- noms réels des champs Employee/User;
- identifiant externe employé réellement observé;
- claim OIDC contenant éventuellement un identifiant employé;
- résolution automatique `(issuer, sub) → employee_external_id`;
- règles organisationnelles propres à l'instance réelle.

Au 2026-09-25, cette frontière reste volontairement fermée : aucun feed Employee/User réel n'a encore été observé dans un environnement d'exécution accessible à la tranche #232. Les noms d'entités proposés antérieurement ne doivent donc pas être codés dans #256 comme s'ils constituaient le contrat ERP.

Avant tout adaptateur concret, #232 doit confirmer à partir du service document / metadata OData réel : le feed retenu, sa clé externe stable, les champs ERP possédés, la règle déterministe de planifiabilité, la relation stable User ↔ Employee et les capacités de pagination/incrémentalité. Les capacités de `RP_Projects` ne sont pas héritées implicitement par le feed Employee.

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

- #232 : contrat OData Employee/User réel + relation identité ↔ employé;
- #223 : OIDC réel;
- #162 : SQL Server réel.

#207 / `RP_Projects` est terminé et ne doit pas être réouvert pour cette tranche.

Une fois #232 suffisamment avancée, #256 devra principalement implémenter l'adaptateur OData Employee/User observé, appliquer la règle de planifiabilité confirmée, projeter uniquement les attributs ERP autoritaires vers `ExternalEmployeeRecord` / la ressource locale, et résoudre automatiquement `(issuer, sub) → employee_external_id` selon la relation réelle. Tant que #232 n'a pas fixé ces éléments, #256 reste bloqué.

Voir aussi [ACUMATICA_ODATA_CONTRACT.md](ACUMATICA_ODATA_CONTRACT.md).
