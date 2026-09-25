# Acumatica — workflow contract-first sans accès ERP développeur

## Objet

Le développement des intégrations Acumatica de RessourcePlanner ne dépend pas d'un accès direct des développeurs ou agents à l'environnement ERP réel.

Les données ERP sont exposées à RessourcePlanner via **OData**. La validation contre l'instance réelle est effectuée par une personne autorisée. Une fois la requête OData validée et sa structure transmise sous forme désensibilisée, le développement doit pouvoir se poursuivre entièrement contre un contrat local reproductible.

Ce document définit ce processus comme règle durable.

## Principe

Le flux de travail canonique est :

```text
PO / opérateur autorisé
  valide le feed/requête OData dans Acumatica
            ↓
  produit un contrat + échantillon anonymisé fidèle
            ↓
CONTRACT GATE
  contrat suffisamment précis pour développer
            ↓
DEV
  implémente adaptateur + parser + sync + tests
  contre fixtures/mock locaux
            ↓
CI
  valide sans dépendre d'Acumatica
            ↓
ENVIRONMENT SMOKE
  PO / opérateur autorisé exécute le smoke réel
  et retourne uniquement les résultats techniques désensibilisés
            ↓
DEV
  corrige le contrat/implémentation si nécessaire
```

Un accès développeur à Acumatica n'est donc **ni requis ni attendu**.

## Responsabilités

### PO / opérateur autorisé

Le PO ou une personne autorisée côté ERP :

- identifie et valide la vue/feed OData réel;
- valide les champs nécessaires;
- confirme les identifiants stables;
- exécute au besoin des requêtes `$filter`, `$orderby`, pagination ou autres capacités;
- fournit un exemple de réponse entièrement anonymisé mais structurellement fidèle;
- répond aux questions métier que la structure seule ne permet pas de trancher;
- exécute les smokes réels qui exigent un accès ERP;
- ne transmet jamais au dépôt, à un agent ou à une PR des données réelles sensibles ou des credentials.

### Développeur / agent

Le développeur :

- traite le contrat documenté et les fixtures anonymisées comme la source de vérité accessible pour l'intégration;
- n'essaie pas de découvrir l'ERP réel par brute force;
- n'exige pas un accès à Acumatica pour implémenter l'adaptateur;
- développe contre des fixtures et, lorsque pertinent, un faux endpoint OData local;
- couvre parsing, pagination, erreurs, nulls, idempotence, atomicité et observabilité sans environnement ERP;
- prépare des requêtes ou outils de smoke sûrs lorsque des observations réelles supplémentaires sont nécessaires;
- arrête uniquement lorsqu'une décision de contrat ou de métier manque réellement.

## Paquet de contrat OData

Chaque intégration OData doit pouvoir être décrite par un paquet de contrat composé au minimum de :

1. **nom logique du feed**;
2. **chemin OData relatif**, sans hostname sensible lorsque celui-ci n'a pas à être public;
3. **format** observé, par exemple Atom/XML;
4. **entité** et namespaces pertinents;
5. **clé externe stable**;
6. **mapping des champs** vers le contrat RessourcePlanner;
7. **sémantique des valeurs nulles et types**;
8. **règles de normalisation**, par exemple `strip()` pour les codes paddés;
9. **capacités OData réellement validées** nécessaires au client;
10. **règles métier** de filtrage/admissibilité;
11. **échantillon anonymisé structurellement fidèle**;
12. **questions encore ouvertes**, s'il en reste.

Tant que ce paquet est suffisamment complet pour l'implémentation demandée, l'absence d'accès ERP direct ne bloque pas le développement.

## Fixtures anonymisées

Les fixtures de test doivent préserver la forme du contrat réel :

- namespaces XML;
- noms exacts des propriétés;
- types OData;
- attributs `m:null`;
- `xml:space="preserve"` lorsque pertinent;
- ordre variable des propriétés si le parser ne doit pas dépendre de l'ordre;
- pagination ou variantes de réponses réellement utilisées;
- cas actifs/inactifs;
- valeurs nulles;
- caractères Unicode;
- identifiants synthétiques cohérents.

Les fixtures ne doivent contenir aucune donnée réelle de :

- client;
- employé;
- projet;
- utilisateur;
- courriel;
- téléphone;
- adresse;
- identifiant confidentiel;
- hostname interne;
- credential.

Une fixture peut être dérivée manuellement d'un retour réel à condition que toutes les valeurs soient remplacées et que seule la structure pertinente soit conservée.

## Faux endpoint OData local

Lorsqu'un adaptateur dépend du comportement HTTP et pas seulement du parsing, les tests peuvent utiliser :

- un transport HTTP simulé;
- un serveur local de test;
- des réponses enregistrées synthétiques.

Le mock doit reproduire uniquement les comportements dont RessourcePlanner dépend réellement, par exemple :

- Atom/XML;
- `$filter`;
- `$orderby`;
- `$top/$skip`;
- pagination;
- HTTP 401/403/429/5xx;
- timeout;
- XML invalide;
- snapshot partiel.

Le mock n'a pas à devenir une réimplémentation générale d'OData.

## Outillage local réutilisable

Le dépôt fournit maintenant un chemin contract-first entièrement local :

- fixtures contractuelles : `tests/fixtures/acumatica/`;
- fixture projet de référence : `tests/fixtures/acumatica/rp_projects_atom.xml`;
- primitives Atom/OData communes : `app/infrastructure/acumatica/odata_atom.py`;
- faux transport HTTP de test : `tests/acumatica_odata_test_support.py`;
- inspecteur de contrat : `tools/inspect_odata_contract.py`;
- template pour un nouveau feed : `docs/integrations/acumatica/CONTRACT_TEMPLATE.md`.

Inspection d'une fixture anonymisée :

```bash
python tools/inspect_odata_contract.py tests/fixtures/acumatica/rp_projects_atom.xml
```

L'inspecteur :

- lit uniquement le fichier local fourni;
- n'effectue aucun appel réseau;
- ne conserve aucune copie;
- affiche les namespaces, noms de champs, types, nullabilité observée et structure Atom utile;
- n'affiche jamais les valeurs des propriétés.

Le faux transport est volontairement limité aux scénarios nécessaires aux adaptateurs RessourcePlanner : réponses Atom/XML synthétiques, routage par paramètres de requête, plusieurs pages, statuts HTTP et erreurs de transport. Il ne simule pas Acumatica en général.

## Validation environnementale réelle

La validation réelle est une étape distincte du développement.

Lorsqu'un smoke ERP est nécessaire, le développeur doit fournir une procédure ou un outil qui :

- reçoit URL/credentials uniquement par environnement ou saisie locale sécurisée;
- effectue des lectures seulement;
- n'écrit aucun secret dans un fichier;
- n'envoie aucun payload réel dans GitHub;
- produit autant que possible un rapport technique désensibilisé.

Exemple de rapport acceptable :

```text
Feed: RP_Employees
HTTP: 200
Format: Atom/XML
Entries: 128
Key field: EmployeeId
$filter: supported
$orderby: supported
$top/$skip: supported
LastModified: present
Null values: observed
```

Le rapport peut confirmer une capacité ou une structure sans exposer les valeurs métier.

## Gates

### CONTRACT GATE

Bloque le développement uniquement lorsque le contrat nécessaire est réellement inconnu.

Exemples :

- feed Employee non identifié;
- clé stable inconnue;
- champ actif/inactif ambigu;
- règle de planifiabilité non décidée.

Le gate est satisfait lorsque le PO fournit un contrat et une fixture suffisants pour coder.

### DEVELOPMENT

Ne dépend pas d'Acumatica réel.

L'adaptateur, le service, les tests et la CI doivent être exécutables entièrement avec des données synthétiques.

### ENVIRONMENT SMOKE

Confirme ensuite les hypothèses qui ne peuvent être prouvées localement :

- authentification réelle;
- capacités du serveur OData;
- performance/volume;
- comportement temporel;
- requête exacte;
- compatibilité sur l'instance réelle.

Un smoke réel peut découvrir un écart de contrat; cet écart déclenche alors une mise à jour du contrat et des fixtures, pas l'ouverture permanente de l'ERP aux développeurs.

## Application aux intégrations connues

### RP_Projects

Le contrat `RP_Projects` est déjà connu, implémenté et validé. Les fixtures anonymisées et les tests permettent maintenant de maintenir l'adaptateur sans dépendre d'un accès ERP direct.

### Employees / Users

Le contract gate principal est maintenant satisfait.

Contrats confirmés :

```text
RP_Employees.EmployeID = clé unique Employee
RP_Users.UserID = clé unique User
RP_Users.EmployeID → RP_Employees.EmployeID
```

Fixtures :

- `tests/fixtures/acumatica/rp_employees_atom.xml`;
- `tests/fixtures/acumatica/rp_users_atom.xml`.

Décision d'autorisation :

- toute nouvelle ressource synchronisée est désactivée localement par défaut;
- toute nouvelle entrée User ERP est désactivée localement par défaut;
- l'état ERP et l'activation RessourcePlanner sont distincts;
- seul un ADMIN active l'usage local et attribue les rôles;
- la synchronisation ERP ne doit jamais accorder automatiquement un rôle ni écraser le choix local.

La relation OIDC `(issuer, subject) → RP_Users.UserID` reste à confirmer séparément. Elle ne bloque pas le développement des adaptateurs OData ni de la surface ADMIN.

Voir `docs/integrations/acumatica/RP_EMPLOYEES_USERS.md`.

### Tâches / budgets

Le PO dispose également d'un feed OData tâches incluant les budgets. Tant que son chemin, sa clé, ses champs budget et sa fixture anonymisée ne sont pas fournis, #271 demeure le fallback temporaire. Ne pas inventer ce contrat.

## Sécurité

Le dépôt est public.

Ne jamais committer :

- credentials ERP;
- hostname privé non nécessaire;
- payload réel non anonymisé;
- cookie/session;
- token;
- secret;
- capture d'écran contenant des données métier;
- export ERP brut.

Le principe est : **exposer le contrat, jamais les données réelles**.

## Références

Voir également :

- [ACUMATICA_ODATA_CONTRACT.md](ACUMATICA_ODATA_CONTRACT.md)
- [ACUMATICA_RESOURCE_FOUNDATION.md](ACUMATICA_RESOURCE_FOUNDATION.md)
- [V2_ACUMATICA_READINESS.md](V2_ACUMATICA_READINESS.md)
- #207
- #232
- #256
