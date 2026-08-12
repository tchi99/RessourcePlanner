# Confidentialité et données de test

RessourcePlanner doit rester séparé des données réelles de production dans GitHub.

## Règles du dépôt

- Ne jamais versionner `app_config.json`.
- Ne jamais versionner de classeur `.xlsx`, `.xlsm` ou `.xlsb` provenant de la production.
- Ne jamais copier dans le code, la documentation, les issues, les PR ou les logs des noms de clients, noms d'employés, adresses, numéros de téléphone, courriels, chemins utilisateurs réels, IP privées ou secrets.
- Utiliser uniquement des exemples génériques (`Utilisateur`, `Entreprise`, `Client Démo`, etc.).

## Vérification automatique

Le workflow **Privacy scan** exécute :

```text
python tools/privacy_scan.py
```

Le scan vérifie le contenu courant du dépôt pour plusieurs formes courantes de données sensibles : courriels, téléphones, codes postaux canadiens, adresses probables, chemins Windows utilisateurs réels, chemins UNC, IP privées et affectations de secrets.

Les valeurs détectées ne sont volontairement jamais imprimées dans les logs : seulement la catégorie, le fichier et le numéro de ligne.

## Noms de clients et d'employés propres à l'entreprise

Un scanner générique ne peut pas déterminer de façon fiable si un nom propre est confidentiel. Pour cette raison, créer localement un fichier :

```text
.privacy_terms.local
```

et inscrire une valeur confidentielle par ligne. Ce fichier est ignoré par Git et ne doit jamais être poussé sur GitHub.

Exemple générique :

```text
# Une valeur confidentielle par ligne
Client Confidentiel
Employe Confidentiel
Nom Projet Interne
```

Puis exécuter localement :

```text
python tools/privacy_scan.py
```

Le script signalera toute occurrence sans afficher la valeur recherchée.

## Données de test

Les tests et captures doivent utiliser un classeur entièrement synthétique. Les noms de ressources, clients, projets et lieux du classeur de démonstration doivent être inventés et ne doivent jamais être dérivés d'un classeur de production.

## Historique Git

Supprimer un fichier ou une chaîne sensible dans un nouveau commit ne la retire pas automatiquement de l'historique Git ni nécessairement des anciennes PR. Si une donnée sensible a déjà été versionnée, une réécriture d'historique et, selon le cas, une purge côté hébergeur peuvent être nécessaires.
