# Microsoft 365 / Graph — brouillons de communications

Cette intégration sert uniquement à créer des **brouillons** Microsoft 365 à partir d'un lot de communications déjà préparé et explicitement approuvé dans RessourcePlanner.

## Garde-fou fonctionnel

Le flux reste volontairement séparé :

1. prévisualiser et réviser les messages;
2. préparer le lot;
3. approuver explicitement le lot;
4. cliquer explicitement sur **Créer brouillons M365**;
5. vérifier les brouillons dans Outlook/Microsoft 365;
6. confirmer séparément le lot comme communiqué lorsque la communication réelle a eu lieu.

L'adaptateur ne contient aucun appel Graph d'envoi et l'approbation ne déclenche aucun effet externe.

## Enregistrement d'application Microsoft Entra

Le serveur utilise le flux OAuth 2.0 `client_credentials` (app-only). L'application Entra doit disposer de l'autorisation Microsoft Graph **Application** suivante :

- `Mail.ReadWrite`

Un consentement administrateur est requis. `Mail.ReadWrite` permet de créer et modifier les messages, mais n'accorde pas `Mail.Send`.

Pour réduire le périmètre, limiter l'accès de l'application à la boîte de planification prévue au moyen des mécanismes Exchange Online/Microsoft 365 appropriés de votre tenant plutôt que de laisser l'application accéder à toutes les boîtes.

## Variables d'environnement

Les quatre variables suivantes sont requises ensemble pour activer le transport :

```text
RESOURCEPLANNER_M365_TENANT_ID=<tenant-guid>
RESOURCEPLANNER_M365_CLIENT_ID=<app-registration-client-id>
RESOURCEPLANNER_M365_CLIENT_SECRET=<secret>
RESOURCEPLANNER_M365_MAILBOX=planning@entreprise.tld
```

Variables optionnelles :

```text
RESOURCEPLANNER_M365_GRAPH_BASE_URL=https://graph.microsoft.com/v1.0
RESOURCEPLANNER_M365_AUTHORITY_HOST=https://login.microsoftonline.com
RESOURCEPLANNER_M365_TIMEOUT_SECONDS=20
```

Si aucune variable M365 n'est fournie, le serveur démarre normalement mais l'action **Créer brouillons M365** retourne une indisponibilité explicite. Si seulement une partie des quatre variables obligatoires est fournie, le démarrage est refusé afin d'éviter une configuration ambiguë.

Le secret n'est jamais inclus dans les résumés de configuration ni dans les messages d'erreur applicatifs.

## Validation avant production

Effectuer le premier essai avec une boîte dédiée et un lot de test approuvé. Vérifier :

- que le nombre de brouillons créés correspond exactement au nombre de messages inclus;
- que les destinataires, objets et corps sont corrects;
- qu'aucun message n'apparaît dans Éléments envoyés;
- que l'audit SQL contient `drafts_provider=microsoft_graph`, le nombre créé, l'auteur et l'horodatage;
- qu'un deuxième clic sur le même lot est refusé;
- qu'un lot devenu stale après modification du planning est refusé avant tout appel Graph.

Après ce smoke test réel, conserver #40 ouvert ou fermé selon les autres éléments de transport/envoi manuel encore souhaités; l'envoi direct n'est volontairement pas inclus dans cette tranche.
