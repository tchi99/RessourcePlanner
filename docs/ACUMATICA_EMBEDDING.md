# Embedding Acumatica — configuration RessourcePlanner

## Objectif

RessourcePlanner peut être servi comme application Web autonome ou être chargé dans une surface Acumatica compatible avec un `iframe`. L'embedding est une commodité de navigation : il ne remplace jamais l'authentification OIDC ni les autorisations RBAC de RessourcePlanner.

## Comportement par défaut

Sans configuration supplémentaire, le runtime envoie :

```http
Content-Security-Policy: frame-ancestors 'none'
```

Aucun site ne peut donc embarquer RessourcePlanner. L'accès direct continue de fonctionner normalement.

## Autoriser une origine Acumatica

Configurer uniquement les origines parentes réellement nécessaires :

```text
RESOURCEPLANNER_FRAME_ANCESTORS=https://erp.example.test
```

Plusieurs origines peuvent être séparées par un espace ou une virgule :

```text
RESOURCEPLANNER_FRAME_ANCESTORS='self' https://erp.example.test https://portal.example.test
```

Règles appliquées par le runtime :

- `*` est refusé;
- `'none'` doit être utilisé seul;
- une origine distante doit utiliser HTTPS;
- les chemins, paramètres, fragments et credentials dans l'URL sont refusés;
- HTTP n'est toléré que pour `localhost`, `127.0.0.1` ou `::1` afin de permettre les essais locaux.

## Cookie OIDC : mode direct vs iframe

Le mode normal conserve :

```text
RESOURCEPLANNER_OIDC_COOKIE_SAMESITE=lax
```

C'est le profil recommandé lorsque RessourcePlanner est ouvert directement ou lorsque le contexte navigateur ne nécessite pas de cookie cross-site.

Si le scénario réel Acumatica charge RessourcePlanner dans un iframe **cross-site** et que le navigateur doit envoyer le cookie de session dans ce contexte, configurer explicitement :

```text
RESOURCEPLANNER_OIDC_COOKIE_SAMESITE=none
RESOURCEPLANNER_OIDC_SECURE_COOKIE=true
```

Le serveur refuse de démarrer avec `SameSite=None` et `Secure=false`.

Valeurs autorisées :

- `lax` — défaut;
- `strict` — politique plus restrictive;
- `none` — uniquement avec cookie sécurisé.

Le cookie reste `HttpOnly` dans tous les modes : React ne reçoit pas le jeton de session.

## HTTPS

Le déploiement iframe réel doit utiliser HTTPS pour RessourcePlanner. Le mode `SameSite=None` nécessite un cookie `Secure`; un déploiement HTTP distant n'est donc pas un profil d'exploitation supporté pour ce scénario.

## Limites navigateur

`SameSite=None; Secure` rend le cookie admissible à un contexte cross-site, mais ne garantit pas que tous les navigateurs ou politiques d'entreprise autoriseront les cookies tiers. La validation réelle doit donc être faite avec les navigateurs supportés par l'organisation.

Si les politiques navigateur empêchent durablement les cookies de session dans l'iframe, conserver l'URL directe RessourcePlanner comme chemin de repli et réévaluer le mécanisme d'intégration au lieu de réduire les protections de cookie ou de CSP.

## Authentification et confiance

Le fait qu'une page soit chargée depuis Acumatica ne prouve aucune identité. Les règles restent :

1. OIDC authentifie l'identité externe;
2. `(issuer, subject)` doit correspondre à un utilisateur local actif;
3. les rôles et permissions sont déterminés par RessourcePlanner;
4. FastAPI applique les autorisations pour chaque route sensible.

Aucun header ou paramètre provenant du parent iframe ne doit accorder un rôle RessourcePlanner.

## Validation locale

Profil direct sécurisé par défaut :

```text
RESOURCEPLANNER_FRAME_ANCESTORS='none'
RESOURCEPLANNER_OIDC_COOKIE_SAMESITE=lax
```

Profil de test iframe local :

```text
RESOURCEPLANNER_FRAME_ANCESTORS=http://localhost:3000
```

Le mode HTTP loopback sert uniquement aux essais locaux du framing; il ne justifie pas de désactiver `Secure` pour un cookie `SameSite=None`.

## Validation réelle

La validation environnementale est suivie dans l'issue #227. Avant de déclarer l'intégration prête :

- confirmer l'origine exacte Acumatica;
- déployer RessourcePlanner en HTTPS;
- vérifier que l'origine autorisée peut embarquer l'application et qu'une autre origine est bloquée;
- vérifier que l'URL directe reste disponible;
- effectuer le login OIDC et le logout dans le scénario retenu;
- vérifier le cookie dans les outils navigateur;
- tester au moins un profil lecture seule et un profil autorisé à modifier;
- documenter seulement la configuration non sensible.

## Variables concernées

```text
RESOURCEPLANNER_FRAME_ANCESTORS
RESOURCEPLANNER_OIDC_COOKIE_SAMESITE
RESOURCEPLANNER_OIDC_SECURE_COOKIE
```

Les paramètres OIDC complets restent documentés dans `docs/OIDC_ACUMATICA_VALIDATION.md`.
