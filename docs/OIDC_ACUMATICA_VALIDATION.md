# Validation réelle OIDC Acumatica

L'implémentation OIDC de RessourcePlanner est testée avec un fournisseur simulé. Ce document sert de checklist lorsque les paramètres de l'instance Acumatica réelle seront disponibles.

## Paramètres requis

- URL de découverte OIDC de l'instance;
- client ID enregistré pour RessourcePlanner;
- credential client si le type de client retenu l'exige;
- redirect URI autorisé vers `/api/v1/auth/callback`;
- scopes autorisés incluant `openid`;
- valeur réelle de l'issuer et format du `subject` retourné.

Ne jamais inscrire de secret ou token réel dans ce document ou dans Git.

## Préparation RessourcePlanner

1. exécuter `alembic upgrade head` afin d'inclure `0010_app_users_identity` et `0011_oidc_sessions`;
2. provisionner un utilisateur de test actif dans `app_users` avec le couple exact `(issuer, subject)` et un rôle RessourcePlanner contrôlé;
3. configurer `RESOURCEPLANNER_AUTH_MODE=oidc`;
4. configurer les variables `RESOURCEPLANNER_OIDC_*` uniquement dans l'environnement d'exécution;
5. utiliser HTTPS et conserver le cookie sécurisé en environnement partagé.

## Smoke attendu

1. ouvrir RessourcePlanner sans session : l'interface doit proposer la connexion;
2. démarrer `/api/v1/auth/login` et vérifier la redirection vers Acumatica;
3. terminer le login et revenir sur `/api/v1/auth/callback` puis `/`;
4. vérifier `/api/v1/auth/me` : issuer, subject, utilisateur local, rôles et permissions attendus;
5. vérifier qu'un utilisateur Acumatica non provisionné est refusé;
6. vérifier les permissions avec au moins deux rôles locaux différents;
7. se déconnecter et confirmer que l'ancienne session ne permet plus `/api/v1/auth/me`;
8. redémarrer l'application et confirmer que les sessions SQL non expirées restent résolubles;
9. confirmer les attributs de cookie en HTTPS (`HttpOnly`, `Secure`, `SameSite=Lax`);
10. documenter uniquement les métadonnées non sensibles retenues : issuer, discovery URL, redirect URI, scopes et procédure de provisionnement.

## Séparation des credentials

L'OIDC interactif ne doit pas réutiliser `RESOURCEPLANNER_ACUMATICA_ACCESS_TOKEN`. Ce dernier appartient à la synchronisation ERP serveur-à-serveur et reste une frontière séparée.
