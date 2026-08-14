# Signature des releases Windows

Les releases Windows de RessourcePlanner doivent être signées en **Authenticode** avant le calcul du SHA-256 et avant leur publication sur GitHub.

Le workflow `.github/workflows/windows-release.yml` est préparé pour **Azure Artifact Signing** (anciennement Trusted Signing). Les builds de pull request restent volontairement non signés; les builds déclenchés manuellement et les tags de release utilisent l'environnement GitHub `release-signing` et échouent si la configuration de signature n'est pas présente.

## Pourquoi Artifact Signing

- certificat Public Trust géré par Microsoft;
- aucune clé privée ou fichier PFX à stocker dans GitHub;
- authentification GitHub → Azure avec OIDC, sans secret client longue durée;
- signature RFC3161 horodatée afin que la signature demeure valide après l'expiration du certificat court terme;
- intégration officielle GitHub Actions avec `azure/artifact-signing-action`.

Une signature valide affiche l'identité de l'éditeur et permet à la réputation de l'éditeur de s'accumuler entre les versions. Elle ne garantit toutefois pas qu'un nouveau binaire ne déclenchera jamais SmartScreen. Pour une absence garantie d'avertissement SmartScreen au téléchargement, Microsoft recommande la distribution MSIX via le Microsoft Store.

## 1. Créer les ressources Azure Artifact Signing

Dans le portail Azure :

1. enregistrer le fournisseur de ressources Artifact Signing si nécessaire;
2. créer un compte Artifact Signing;
3. effectuer la validation d'identité;
4. créer un profil de certificat **Public Trust**;
5. conserver les trois informations suivantes :
   - endpoint régional, par exemple `https://eus.codesigning.azure.net/`;
   - nom du compte Artifact Signing;
   - nom du profil de certificat.

La validation d'identité doit être terminée dans le portail Azure avant de pouvoir signer.

## 2. Créer l'identité GitHub Actions dans Microsoft Entra ID

Créer une application Microsoft Entra (ou une identité managée appropriée), puis ajouter une **Federated credential** :

- scénario : `GitHub actions deploying Azure resources`;
- dépôt : `tchi99/RessourcePlanner`;
- type d'entité : **Environment**;
- environnement : `release-signing`.

L'utilisation d'un environnement GitHub limite le jeton OIDC au job de release et permet d'ajouter des règles de protection. Utiliser l'assistant Azure/GitHub plutôt que de saisir manuellement la revendication `sub`, afin de rester compatible avec les formats de revendication OIDC immuables récents de GitHub.

Attribuer ensuite à cette identité le rôle **Artifact Signing Certificate Profile Signer** sur le profil ou sur la portée minimale permettant de signer.

## 3. Configurer l'environnement GitHub `release-signing`

Dans **Settings → Environments**, créer `release-signing`.

Ajouter les secrets :

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Ajouter les variables :

- `AZURE_ARTIFACT_SIGNING_ENDPOINT`
- `AZURE_ARTIFACT_SIGNING_ACCOUNT`
- `AZURE_ARTIFACT_SIGNING_PROFILE`

Aucune clé privée de certificat ne doit être ajoutée au dépôt ou aux secrets GitHub.

Il est recommandé de restreindre l'environnement `release-signing` aux tags de release et, si souhaité, d'exiger une approbation manuelle avant l'accès aux informations de signature.

## 4. Tester la signature sans publier de release

Dans **Actions → Windows desktop package → Run workflow**, entrer une version de test, par exemple :

`1.8.0-signing-test`

Le job doit :

1. construire l'EXE;
2. se connecter à Azure par OIDC;
3. signer l'EXE avec Artifact Signing;
4. valider `Get-AuthenticodeSignature` avec le statut `Valid`;
5. calculer le SHA-256 **après** signature;
6. déposer l'EXE signé comme artifact CI.

Cette exécution manuelle ne crée pas de GitHub Release.

## 5. Publier une release officielle

Une fois le test de signature concluant, créer/pousser un tag au format :

`vX.Y.Z`

Exemple : `v1.8.0`.

Le workflow construit et signe le binaire, vérifie la signature, calcule son checksum puis crée la GitHub Release. Une release officielle ne doit plus être publiée si la signature échoue.

## Vérification locale

Après téléchargement d'une release :

```powershell
Get-AuthenticodeSignature .\RessourcePlanner-VX.Y.Z-Windows-x64.exe | Format-List Status,StatusMessage,SignerCertificate,TimeStamperCertificate
```

Le champ `Status` doit être `Valid`.

## Règles de sécurité

- ne jamais committer un `.pfx`, une clé privée ou un mot de passe de certificat;
- produire le checksum seulement après la signature, car la signature modifie le fichier;
- conserver la même identité d'éditeur entre les releases afin de permettre l'accumulation de réputation;
- ne jamais republier silencieusement un binaire différent sous le même tag sans raison explicite;
- conserver le workflow de pull request non signé : les secrets et permissions de signature ne sont nécessaires que pour les releases.
