# Signature des releases Windows

Les releases Windows de RessourcePlanner utilisent un **certificat Authenticode auto-signé interne**. Cette solution ne coûte rien, mais le certificat doit être explicitement approuvé sur chaque poste qui exécute l'application (ou déployé par GPO/Intune dans un environnement géré).

Le workflow `.github/workflows/windows-release.yml` fonctionne ainsi :

- les builds de pull request restent non signés et n'accèdent à aucun secret;
- les builds manuels et les tags `v*` utilisent l'environnement GitHub `release-signing`;
- le PFX est reconstruit uniquement dans le runner Windows éphémère à partir de secrets GitHub;
- l'EXE est signé en SHA-256 avec SignTool et horodaté RFC3161;
- la signature est vérifiée avant calcul du checksum;
- le certificat public `.cer` est publié avec chaque artifact/release afin de pouvoir installer la confiance sur les postes internes.

## Limite importante

Un certificat auto-signé n'est pas reconnu publiquement par Windows. Sur un poste qui **n'a pas installé notre certificat public comme approuvé**, l'EXE ne bénéficiera pas d'une chaîne de confiance publique et SmartScreen peut continuer à avertir l'utilisateur.

Sur les postes internes où le certificat est installé dans les magasins appropriés, Windows peut vérifier l'identité du signataire et l'intégrité du fichier avec Authenticode.

## 1. Créer le certificat une seule fois

Sur un poste Windows de confiance, ouvrir PowerShell et exécuter depuis le dépôt :

```powershell
.\tools\create_internal_code_signing_certificate.ps1 -CopyPfxBase64ToClipboard
```

Par défaut, le script crée un certificat :

- sujet : `CN=RessourcePlanner Internal Code Signing`;
- EKU : Code Signing;
- RSA 3072 bits;
- SHA-256;
- durée : 5 ans;
- clé exportable pour pouvoir signer dans GitHub Actions.

Le script demande un mot de passe fort pour protéger le PFX et génère :

- `RessourcePlanner-Internal-CodeSigning.pfx` : **clé privée — secret critique**;
- `RessourcePlanner-Internal-CodeSigning.cer` : certificat public, distribuable sans risque.

Avec `-CopyPfxBase64ToClipboard`, le contenu Base64 du PFX est copié au presse-papiers pour être collé directement dans GitHub Secrets.

Le dossier `signing-output` est uniquement un espace de travail local. Ne jamais ajouter le PFX au dépôt, à OneDrive/SharePoint ou à un courriel.

## 2. Configurer GitHub

Dans le dépôt GitHub :

1. ouvrir **Settings → Environments**;
2. créer ou ouvrir l'environnement `release-signing`;
3. ajouter les secrets suivants :
   - `CODE_SIGNING_PFX_BASE64` : contenu Base64 du PFX;
   - `CODE_SIGNING_PFX_PASSWORD` : mot de passe choisi lors de l'export du PFX.

Aucune clé privée n'est enregistrée dans le code ou dans le dépôt. GitHub documente l'utilisation de Base64 pour stocker un petit blob binaire dans un secret Actions; Base64 n'est pas un chiffrement, la confidentialité est assurée par le secret GitHub lui-même.

Après avoir configuré les secrets, conserver le PFX dans un emplacement hors ligne sécurisé ou supprimer la copie de travail locale.

## 3. Tester la signature sans publier de release

Dans **Actions → Windows desktop package → Run workflow**, entrer une version de test, par exemple :

`1.8.0-signing-test`

Le job doit :

1. construire l'EXE;
2. reconstruire/importer temporairement le PFX dans `CurrentUser\My` sur le runner;
3. signer l'EXE avec SignTool (`/fd SHA256`);
4. appliquer un horodatage RFC3161 SHA-256;
5. vérifier que le certificat signataire correspond exactement au certificat attendu;
6. vérifier qu'un certificat d'horodatage est présent et que sa chaîne publique est valide;
7. valider la chaîne du certificat auto-signé avec une chaîne de confiance personnalisée en mémoire, sans modifier le magasin Root du runner;
8. rejeter tout statut Authenticode autre que `Valid` ou le cas précis `UnknownError` causé uniquement par la racine privée non approuvée du runner;
9. calculer le SHA-256 après signature;
10. publier comme artifact l'EXE, le checksum et le `.cer` public;
11. supprimer le matériel de signature temporaire du runner.

Le runner GitHub n'est volontairement pas configuré pour approuver publiquement notre certificat auto-signé. Il peut donc afficher un diagnostic de racine non approuvée même lorsque la signature, l'identité du signataire, l'horodatage et la chaîne personnalisée sont correctement validés.

L'exécution manuelle ne crée pas de GitHub Release.

## 4. Installer la confiance sur un poste interne

Télécharger `RessourcePlanner-Internal-CodeSigning.cer` depuis une release officielle.

Pour qu'un poste Windows interne traite ce certificat auto-signé comme une ancre de confiance, installer le certificat public dans :

- **Trusted Root Certification Authorities**;
- **Trusted Publishers**.

Avec un certificat auto-signé, la confiance ne provient d'aucune autorité de certification publique : le poste doit donc explicitement approuver ce certificat comme racine de confiance interne. `Trusted Publishers` établit en plus la confiance envers cet éditeur Authenticode pour les systèmes internes.

Pour tous les utilisateurs d'un PC, utiliser les magasins **Local Computer** (droits administrateur requis). Pour un seul utilisateur, les magasins Current User peuvent suffire selon la politique Windows locale.

En entreprise, le meilleur déploiement est généralement GPO ou Intune afin que tous les postes reçoivent exactement le même certificat public.

Ne jamais installer le fichier `.pfx` sur les postes utilisateurs : seul le `.cer` public doit être distribué.

## 5. Publier une release officielle

Créer/pousser un tag :

`vX.Y.Z`

Le workflow refuse de publier la release si la configuration de signature manque ou si les contrôles Authenticode échouent.

Chaque release contient :

- `RessourcePlanner-VX.Y.Z-Windows-x64.exe`;
- `RessourcePlanner-VX.Y.Z-Windows-x64.exe.sha256`;
- `RessourcePlanner-Internal-CodeSigning.cer`.

## Vérification locale

Après installation du certificat public dans les magasins de confiance du poste :

```powershell
Get-AuthenticodeSignature .\RessourcePlanner-VX.Y.Z-Windows-x64.exe |
    Format-List Status,StatusMessage,SignerCertificate,TimeStamperCertificate
```

Le statut attendu sur un poste correctement configuré est `Valid`.

## Rotation / expiration

Le certificat doit rester le même entre les releases afin de conserver une identité interne stable. Grâce à l'horodatage, une release signée pendant la période de validité conserve la preuve de sa date de signature.

Avant l'expiration du certificat :

1. créer un nouveau certificat;
2. déployer son `.cer` sur les postes **avant** de commencer à signer avec lui;
3. remplacer les deux secrets GitHub;
4. conserver l'ancien certificat public sur les postes tant que d'anciennes releases doivent rester vérifiables.

## Règles de sécurité

- ne jamais committer un `.pfx`, une clé privée, un export Base64 du PFX ou un mot de passe;
- ne jamais distribuer le PFX aux utilisateurs;
- ne jamais stocker le PFX dans le classeur Excel ou dans son dossier partagé;
- limiter l'accès à l'environnement GitHub `release-signing`;
- produire le checksum uniquement après la signature;
- si la clé privée est soupçonnée compromise, cesser immédiatement de l'utiliser et effectuer une rotation du certificat.
