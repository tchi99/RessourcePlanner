# RessourcePlanner Dev Cockpit

Outil de développement local, isolé fonctionnellement de l'application métier RessourcePlanner. Il observe GitHub en lecture seule et génère un prompt court à copier dans un Dev ChatGPT. Il n'intègre aucune API IA/OpenAI et ne pilote aucun agent.

## Source de vérité

Le cockpit ne crée aucun roadmap parallèle. Il lit notamment :

- le roadmap maître GitHub configuré (`#55` par défaut);
- l'issue active et ses sous-tranches;
- les PR, branches, commits, Actions et jobs GitHub;
- `AGENTS.md` pour déterminer si l'enchaînement d'un même bloc est documenté;
- `docs/architecture/` pour signaler les ADR disponibles/applicables.

Une branche ou un commit n'est jamais considéré comme une preuve de `DONE`. Une PR fusionnée alors que l'issue/roadmap n'est pas explicitement à jour est signalée comme un décalage à régulariser.

## Architecture

```text
React + TypeScript + Vite
          ↓ same-origin /api
FastAPI Dev Cockpit
          ↓
GitHub REST API
```

Le build React est servi directement par FastAPI dans l'image finale. Aucune base SQL n'est utilisée.

## Docker Compose

Le service est disponible uniquement avec le profil `dev-tools` :

```bash
docker compose --profile dev-tools up -d --build
```

Adresses locales :

```text
RessourcePlanner  http://127.0.0.1:8080
Dev Cockpit       http://127.0.0.1:8081
```

Le service `dev-cockpit` est publié sur `127.0.0.1` seulement par défaut et utilise `restart: "no"`. Il doit donc être activé explicitement; un redémarrage de Docker/Ubuntu ne doit pas en faire un service persistant par accident.

Le runtime métier normal reste inchangé :

```bash
docker compose up -d --build
```

ne démarre pas le cockpit.

La cible de production est la VM Ubuntu documentée dans [`docs/DEPLOYMENT_UBUNTU_VM.md`](../docs/DEPLOYMENT_UBUNTU_VM.md). Sur cette VM de production, ne pas activer `dev-tools`, ne pas provisionner de `DEV_COCKPIT_GITHUB_TOKEN` et ne pas intégrer le cockpit aux commandes de promotion/rollback.

## Configuration

Variables lues depuis le `.env` racine par Docker Compose :

```dotenv
DEV_COCKPIT_GITHUB_TOKEN=
DEV_COCKPIT_REPOSITORY=tchi99/RessourcePlanner
DEV_COCKPIT_ROADMAP_ISSUE=55
DEV_COCKPIT_STALLED_AFTER_MINUTES=30
DEV_COCKPIT_HTTP_PORT=8081
```

`DEV_COCKPIT_GITHUB_TOKEN` doit être un token GitHub local en lecture seule donnant accès au dépôt surveillé, aux Issues, PR et Actions. Le token :

- n'est jamais envoyé à React;
- n'est jamais retourné par l'API;
- n'est pas écrit dans les logs applicatifs;
- ne doit jamais être committé.

Sans token, `/api/dashboard` retourne une erreur de configuration explicite plutôt que d'essayer silencieusement un accès non authentifié.

## Rôles et conversations ChatGPT

Le cockpit affiche une petite équipe visuelle configurable (Product Owner, Developer et Architecte par défaut).

La configuration se fait entièrement dans l'interface avec **Gérer les rôles**. Aucun fichier JSON n'a besoin d'être modifié manuellement. Pour chaque rôle, l'UI permet de :

- modifier le nom et l'identifiant;
- choisir un avatar prédéfini;
- associer l'URL d'une conversation ChatGPT;
- activer/désactiver le rôle;
- réordonner ou supprimer le rôle;
- ajouter de nouveaux rôles.

Le lien ChatGPT ouvre la conversation dans un nouvel onglet. Le cockpit n'embarque pas ChatGPT dans un iframe et n'utilise aucune API OpenAI.

Les bulles affichées sur les cartes sont dérivées des données déjà connues du cockpit. Le rôle avec l'avatar `developer` reflète notamment READY, travail en cours, CI, mergeabilité et stalls; son avatar reçoit une animation CSS légère quand une activité de développement est observée. Les autres rôles affichent des informations contextuelles simples provenant du roadmap, des ADR ou de la CI.

Cette configuration est uniquement une **préférence locale de présentation**. Elle ne devient jamais une source de vérité sur l'état produit ou le roadmap.

### Panneaux interactifs par rôle

Les cartes de rôles servent aussi de points d'entrée vers un panneau latéral contextuel. Le panneau s'ouvre depuis l'avatar, le nom ou le bouton **Voir détails**.

Les vues spécialisées chargent maintenant le détail GitHub **à la demande** :

- **Product Owner** : roadmap maître complet; chaque issue devient un accordéon qui charge son corps GitHub réel, ses sections et sa documentation référencée;
- **Developer** : section exacte de la sous-tranche active extraite de l'issue parent, contexte complet de l'issue, HEAD de la branche active, statistiques/fichiers du commit, documentation et ADR associés, PR/CI, diagnostic de stall et prompt de reprise;
- **Architecte** : contenu réel de `docs/architecture/README.md`, contexte de la sous-tranche active, ADR pertinents puis autres ADR, tous lisibles dans des accordéons sans quitter le cockpit;
- **Reviewer** : jobs CI en échec et PR ouvertes;
- **Generic** : vue minimale et état de la conversation associée.

Le `Dashboard` reste volontairement léger. Les panneaux utilisent des routes de détail séparées :

```text
GET /api/details/roadmap
GET /api/details/issues/{number}
GET /api/details/commits/{sha}
GET /api/details/architecture
```

Ces routes utilisent le même accès GitHub en lecture seule et ne sont invoquées que lorsque la vue concernée est ouverte. GitHub demeure la source de vérité; aucun contenu n'est recopié dans une base locale.

Le panneau peut être fermé avec le bouton ×, en cliquant à l'extérieur ou avec la touche `Escape`. Sur mobile, il occupe toute la largeur.

### Firefox Companion — état réel des conversations

Le sous-dossier [`firefox-companion/`](firefox-companion/) contient une WebExtension Firefox locale. Elle permet d'animer n'importe quel rôle à partir de l'état réel de la conversation associée, sans API OpenAI.

Le matching se fait par l'URL de conversation configurée dans `chat_url` :

```text
rôle Product Owner
chat_url = https://chatgpt.com/c/abc
          ↓
Firefox Companion heartbeat pour /c/abc
          ↓
Product Owner → ChatGPT · working
```

États navigateur exposés par le cockpit :

- `working` : contrôle Stop de génération détecté;
- `idle` : conversation ouverte sans génération;
- `possible_stall` : la dernière trace était `working`, mais aucun heartbeat depuis 30 s;
- `disconnected` : la dernière trace était `idle`, puis le heartbeat a disparu.

Un passage `working → idle` conserve aussi brièvement un signal « réponse terminée ».

Le navigateur et GitHub restent deux sources séparées : un rôle Developer peut être animé par GitHub, par ChatGPT, ou par les deux. Pour les autres rôles, l'état ChatGPT suffit à déclencher l'animation.

Installation Firefox détaillée : [`firefox-companion/README.md`](firefox-companion/README.md).

### Persistance

Le backend sauvegarde la configuration dans :

```text
/data/roles.json
```

avec une écriture atomique. En Docker, `/data` est relié au volume nommé :

```text
dev-cockpit-data
```

Ainsi, un rebuild ou un redémarrage du conteneur conserve les rôles et liens configurés.

```bash
docker compose down
```

conserve le volume. En revanche :

```bash
docker compose down -v
```

supprime les volumes locaux, **incluant la configuration des rôles du cockpit**.

Les endpoints locaux correspondants sont `GET /api/roles` et `PUT /api/roles`. Ils restent servis uniquement par le backend cockpit sur l'interface loopback exposée par Compose.

### Résolution de la branche de travail active

Le cockpit ne doit pas utiliser le dernier commit de `main` pour déterminer l'activité du Developer.

Pour la tranche active, la résolution suit cet ordre :

1. branche `head` de la PR correspondante, si une PR existe;
2. sinon, recherche d'une branche dont le nom correspond à la clé de travail active (`332A`, `13C`, etc.);
3. la recherche parcourt **toutes les pages de branches GitHub**, et non seulement les 100 premières;
4. si plusieurs branches correspondent, celle dont le HEAD a le commit le plus récent est retenue.

La clé de travail active vient d'abord de l'état documenté dans l'issue/roadmap. Les sous-tranches marquées `✅` ou explicitement `DONE` sont considérées terminées; le resolver avance donc vers la première sous-tranche restante avant de rechercher sa branche.

Le commit de `main` affiché dans le footer est uniquement une référence sur l'état du dépôt. Les états `IN_PROGRESS`, `STALLED`, la dernière activité, les workflows associés et le détail Developer utilisent le HEAD de la branche active ou de la PR active.

## Pipeline produit explicite du roadmap #55

Lorsque #55 contient une section dont le heading annonce une `Suite produit` ou un `Pipeline produit`, ce **pipeline produit explicite devient la source canonique du focus courant** : il détermine l'issue/sous-tranche DEV active utilisée pour les PR, branches, CI, stalls et prompts. Le resolver historique basé sur `Ordre actif :` reste seulement un fallback de compatibilité pour les roadmaps plus anciens qui n'ont pas encore de pipeline explicite.

Le contrat actuellement documenté dans #55 est déterministe :

1. la séquence ordonnée est le premier bloc fenced `text` de cette section qui contient des références `#issue` / `#issueSousTranche`;
2. une étape ordinaire est `WORK`;
3. une étape explicitement libellée ASTRA / analyse architecturale est `ARCHITECTURE_GATE`;
4. une étape explicitement libellée validation VM / environnement / infrastructure est `ENVIRONMENT_GATE`;
5. la table Markdown de la même section peut enrichir le type et surtout l'état de la gate;
6. `✅` ou une formulation explicite de gate terminée/satisfaite/validée dans #55 marque la gate comme franchie;
7. les sous-tranches WORK continuent aussi de réutiliser les marqueurs GitHub de l'issue active.

Aucun état local n'enregistre qu'une gate est terminée. Si #55 ne la marque plus comme satisfaite, le Cockpit la reconsidère comme ouverte au prochain refresh.

Exemple de trajectoire :

```text
WORK → WORK → WORK
          ↓
ARCHITECTURE_GATE
          ↓
WORK → WORK → WORK
          ↓
ENVIRONMENT_GATE
```

Le dashboard principal affiche une projection compacte du pipeline sous **Maintenant / Parallèle disponible / Ensuite**. Le panneau **Product Owner** conserve la trajectoire détaillée et rétractable sous **Maintenant / En parallèle / Ensuite / Plus tard**.

Une ligne du bloc de trajectoire qui commence explicitement par `En parallèle` est classée dans la lane `PARALLEL`. Elle reste visible comme travail READY indépendant mais **ne bloque jamais l'avancement de la lane principale**. Les mentions simplement descriptives de parallélisme dans la table ou dans une justification ne changent pas automatiquement la lane.

Chaque step y est lui-même rétractable :
- une sous-tranche DEV charge la section exacte de son issue parent;
- une issue DEV charge son contenu GitHub;
- une gate affiche son type, son état et sa justification tirés de #55, avec le contexte de l'issue cible et la documentation associée.

Une gate d'architecture ou d'environnement n'est jamais transformée en tranche DEV. Si elle devient le step courant, le prompt Developer indique explicitement qu'aucune implémentation ne doit démarrer avant que GitHub/#55 documente la gate comme satisfaite.


### PR d'architecture vs travail Developer

Une PR liée à l'issue active n'est pas automatiquement considérée comme une PR d'implémentation. Le Cockpit inspecte les fichiers changés des PR qui correspondent à la tranche active :

- une PR dont tous les fichiers sont documentaires (`docs/**` ou fichiers Markdown) reste visible dans les listes générales mais n'est pas utilisée comme `primary_pr` du Developer;
- une PR docs-only fusionnée ne déclenche pas l'état « PR fusionnée mais tranche non terminée »;
- une PR qui touche du code, des tests, des migrations, de la configuration ou tout autre fichier non documentaire reste une PR DEV;
- si la liste des fichiers d'une PR n'est pas disponible, le Cockpit reste conservateur et la considère comme potentiellement DEV plutôt que de masquer un vrai travail.

Cela permet à une analyse d'architecture de matérialiser un ADR dans une PR sans faire croire que la première sous-tranche DEV a commencé ou a été livrée.

Quand `AGENTS.md` autorise l'enchaînement et que l'issue documente un ordre obligatoire, le prompt Developer énumère désormais explicitement la chaîne restante (par exemple `291A → 291B → …`) au lieu d'un simple « poursuivre le bloc ».

## Détection du travail interrompu

Le cockpit ne considère pas le dernier commit global du dépôt comme un signal de stall. Il observe uniquement l'activité GitHub pertinente pour la tranche active.

Le même seuil `DEV_COCKPIT_STALLED_AFTER_MINUTES` alimente trois niveaux :

```text
STALLED_CONFIRMED
CI rouge + aucun workflow actif + aucune reprise/commit depuis le seuil

STALLED
branche ou PR de la tranche active + aucune activité pertinente depuis le seuil
+ aucun workflow actif

POSSIBLE_STALL
tranche explicitement marquée 🟡 / en cours dans GitHub
+ aucune branche/PR/workflow associé visible
+ aucun changement pertinent depuis le seuil
```

L'activité pertinente est dérivée du commit de la branche active, de la PR, des workflows du SHA actif et, lorsqu'aucun artefact de travail n'existe encore, de la mise à jour explicite de l'issue active. Un workflow en cours empêche toujours l'état de stall.

Cette logique est volontairement prudente : elle peut signaler qu'un Dev ChatGPT semble arrêté, mais elle ne prétend pas connaître l'état de l'interface ChatGPT ni un travail non publié qui n'existe pas dans GitHub.

## Développement local hors Docker

Backend :

```bash
python -m pip install -r dev-cockpit/backend/requirements.txt
cd dev-cockpit/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Frontend :

```bash
cd dev-cockpit/frontend
npm install
npm run dev
```

Vite écoute sur `127.0.0.1:5174` et relaie `/api` vers `127.0.0.1:8001`.

## Tests

```bash
cd dev-cockpit/backend
python -m unittest discover -s tests -v
cd ../frontend
npm install --no-audit --no-fund
npm run build
```

Validation Compose :

```bash
docker compose config
docker compose --profile dev-tools config
```

Smoke ciblé du chemin réellement documenté :

```bash
docker compose --profile dev-tools up -d --build
curl http://127.0.0.1:8080/ready
curl http://127.0.0.1:8081/api/health
curl http://127.0.0.1:8081/api/config
```

La CI vérifie également que `docker compose config --services` n'inclut pas `dev-cockpit` sans profil, alors que `docker compose --profile dev-tools config --services` l'inclut.
