# Firefox Companion — Dev Cockpit

Extension WebExtension locale pour relayer l'état visuel d'une conversation ChatGPT vers le Dev Cockpit, sans API OpenAI.

## Données transmises

Le Companion n'envoie jamais le texte d'une conversation. Le heartbeat contient uniquement :

- l'URL de la conversation ChatGPT;
- `working` ou `idle`;
- si l'onglet est visible;
- si l'onglet a le focus;
- un signal fixe `stop-control` / `none`.

Le backend normalise l'URL et la compare au `chat_url` configuré pour chaque rôle dans le cockpit.

## Installation locale dans Firefox

1. démarrer le Dev Cockpit;
2. ouvrir `about:debugging#/runtime/this-firefox`;
3. cliquer **Load Temporary Add-on…**;
4. sélectionner `dev-cockpit/firefox-companion/manifest.json`;
5. cliquer l'icône **Dev Cockpit Companion** dans Firefox pour ouvrir les options;
6. conserver `http://127.0.0.1:8081` ou saisir le port local configuré;
7. cliquer **Tester la connexion**.

L'extension temporaire est déchargée lorsque Firefox redémarre. Il faut alors refaire les étapes 2 à 4. Une distribution persistante demanderait un packaging/signing Firefox séparé et n'est pas nécessaire au MVP local.

## Détection

Le content script observe uniquement les contrôles UI de génération. Plusieurs signaux accessibles sont utilisés, notamment les identifiants de bouton Stop connus et les libellés accessibles anglais/français. Aucun sélecteur ne lit le contenu des messages.

Le content script :

- envoie un heartbeat toutes les 5 secondes;
- envoie aussi rapidement un heartbeat lorsque le DOM pertinent change;
- suit automatiquement les changements d'URL d'une conversation;
- fonctionne pour les rôles indépendamment de leur avatar.

Le backend considère un heartbeat comme stale après 30 secondes :

- dernier état `working` → `possible_stall`;
- dernier état `idle` → `disconnected`.

Lorsqu'une conversation passe de `working` à `idle`, le cockpit conserve un signal de fin de réponse afin d'afficher brièvement que ChatGPT vient de terminer.

## Sécurité

Les appels sortants du background sont limités aux adresses loopback `127.0.0.1` et `localhost`. L'extension ne possède aucun token GitHub ou OpenAI.
