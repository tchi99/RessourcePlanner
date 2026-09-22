# Déploiement cible — VM Ubuntu sur Synology

## Décision

RessourcePlanner n'est plus destiné à être déployé directement dans **Synology Container Manager**.

La cible d'exploitation privilégiée est maintenant une **VM Ubuntu dédiée**, hébergée sur le Synology, dans laquelle tournent Docker Engine et Docker Compose.

Le Synology agit donc comme hôte de virtualisation; le runtime applicatif reste un environnement Linux standard indépendant de DSM.

## Architecture cible

```text
Utilisateurs
    |
    v
Synology
└── VM Ubuntu
    ├── Docker Engine
    ├── Docker Compose
    ├── frontend React / Nginx :8080
    ├── backend FastAPI :8000 (réseau Docker)
    └── services/outils auxiliaires explicitement activés
            |
            +---- SQL Server externe
            +---- Acumatica / OIDC
            +---- Microsoft 365 / SMTP
```

SQL Server reste externe à la VM sauf décision explicite contraire.

## Pourquoi cette cible

Cette approche permet notamment :

- un environnement Linux standard et reproductible;
- une séparation nette entre DSM et le runtime applicatif;
- une installation Docker/Compose classique;
- des mises à jour et diagnostics indépendants des particularités de Synology Container Manager;
- une restauration ou reconstruction de la VM plus prévisible;
- une meilleure isolation des outils de développement ou d'administration.

## Préparation de la VM

Base recommandée :

- Ubuntu Server LTS;
- Docker Engine;
- plugin Docker Compose v2;
- Git seulement si le mode de promotion retenu utilise un checkout local;
- synchronisation horaire/NTP;
- stockage persistant prévu pour les volumes applicatifs;
- accès réseau sortant vers SQL Server et les intégrations nécessaires.

À relever avant mise en production :

```bash
uname -a
lsb_release -a
docker version
docker compose version
free -h
df -h
```

## Déploiement

Le packaging applicatif reste Docker/Compose.

La promotion de production reste **explicite** :

1. choisir un commit/release dont la CI est verte;
2. utiliser des images identifiables par tag;
3. conserver le tag actuellement en production;
4. vérifier la compatibilité des migrations;
5. exécuter explicitement `alembic upgrade head`;
6. démarrer les conteneurs;
7. vérifier `/health`, `/ready`, le frontend et un appel API;
8. conserver l'image précédente pendant la fenêtre de validation.

Le déploiement ne doit pas être déclenché silencieusement par chaque push Git.

## Configuration et secrets

Les secrets restent hors Git et hors images Docker.

La VM fournit les variables d'environnement requises pour :

- SQL Server;
- OIDC;
- Acumatica;
- Microsoft 365;
- SMTP;
- clés de chiffrement;
- paramètres réseau/site.

Le mode d'authentification local et le sélecteur d'identité de développement ne doivent pas être activés en production.

## Ports

Le runtime RessourcePlanner conserve son port HTTP public configuré, actuellement typiquement :

```text
8080
```

Les ports backend internes restent confinés au réseau Docker lorsque possible.

Les outils de développement auxiliaires, comme le Dev Cockpit, doivent utiliser un port distinct et ne pas être publiés par défaut sur le LAN de production.

## Dev Cockpit

Le Dev Cockpit est un outil de développement et d'exploitation locale, pas une dépendance du runtime métier.

S'il est intégré au Compose du dépôt, privilégier :

```bash
docker compose --profile dev-tools up -d --build
```

avec une publication locale telle que :

```text
127.0.0.1:8081
```

Il ne doit pas être démarré automatiquement avec le runtime de production.

## SQL Server

La validation réelle du driver ODBC, des migrations et de la connectivité SQL Server reste suivie par #162.

La VM Ubuntu devient l'environnement depuis lequel seront effectués les smokes réseau et ODBC de production.

## Mise à jour et rollback

Avant une promotion, noter :

```text
CURRENT_TAG=<tag actuel>
NEXT_TAG=<tag cible>
ALEMBIC_REVISION=<révision actuelle>
```

En cas de rollback applicatif :

1. vérifier la compatibilité du schéma courant avec l'ancienne image;
2. restaurer le tag applicatif précédent;
3. redémarrer les conteneurs;
4. rejouer les probes et smokes métier.

Ne jamais automatiser un `alembic downgrade` lors d'un rollback de code.

## Sauvegarde / restauration

La stratégie de sauvegarde doit considérer séparément :

- la VM Ubuntu et sa configuration;
- les volumes Docker persistants;
- les secrets/configuration site;
- la base SQL Server externe;
- les images/tags applicatifs.

La sauvegarde du NAS ou de la VM ne remplace pas la stratégie de sauvegarde SQL Server.

## Ancienne cible directe Synology

La procédure précédente de déploiement direct dans Synology Container Manager est conservée dans [`DOCKER_SYNOLOGY.md`](DOCKER_SYNOLOGY.md) uniquement comme référence historique pendant la transition.

Les artefacts `deploy/synology/` pourront être renommés ou retirés dans une tranche dédiée lorsque le nouveau chemin Ubuntu aura été validé en environnement réel.
