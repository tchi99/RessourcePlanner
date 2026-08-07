# Planification MO — V1.1

Application locale Python pour piloter un classeur Excel de planification, y compris un classeur stocké dans un dossier **OneDrive synchronisé localement**.

## Le fichier Excel n'est pas inclus

Le dépôt ne doit contenir aucun fichier `.xlsx` ou `.xlsm`. Au premier lancement, va dans **Paramètres** et choisis ton propre classeur.

## Configuration locale

Le fichier `app_config.json` est **local au poste** et n'est pas versionné dans Git. Il contient notamment le chemin vers le classeur Excel choisi dans l'application.

Un modèle est fourni dans `app_config.example.json` :

```json
{
  "workbook": "",
  "refresh_seconds": 3,
  "save_on_write": true,
  "host": "127.0.0.1",
  "port": 8080
}
```

L'application peut fonctionner même si `app_config.json` n'existe pas encore; le chemin du classeur peut être défini depuis **Paramètres** puis enregistré localement.

## Choisir le fichier Excel

1. Lance `Lancer_Application.bat`.
2. Ouvre **Paramètres**.
3. Clique **Parcourir...** ou colle le chemin complet.
4. Sélectionne ton fichier `.xlsx` ou `.xlsm`.
5. Clique **Tester et enregistrer**.

Le chemin est ensuite conservé localement dans `app_config.json` et peut être modifié à tout moment depuis l'application.

## OneDrive

Utilise le **chemin Windows local synchronisé**, par exemple :

```text
C:\Users\Utilisateur\OneDrive - Entreprise\Planification\PlanificationMoyenLongTerme.xlsx
```

Les URL `https://...sharepoint.com/...` et `https://onedrive.live.com/...` ne sont pas utilisées directement par `xlwings`.

### Recommandation

Dans l'Explorateur Windows, fais un clic droit sur le fichier ou son dossier OneDrive et choisis **Toujours conserver sur cet appareil**.

## Synchronisation

```text
Application Python
      ↓ écriture immédiate
Microsoft Excel / fichier local OneDrive
      ↓
Client OneDrive
      ↓
Microsoft 365
```

Les changements faits directement dans Excel sont relus par l'application environ toutes les 3 secondes.

## Fonctions

- tableau de bord;
- planification style Microsoft Shifts;
- demandes / approbations;
- historique;
- création d'affectations dans `Liste_Effort`;
- navigation dans les feuilles Excel;
- édition des feuilles maîtres;
- protection des formules;
- changement du classeur source dans **Paramètres**.

## Feuilles ajoutées automatiquement

Si elles n'existent pas, la première connexion ajoute au classeur sélectionné :

- `DemandesMO`
- `Historique`

Commence donc idéalement avec une copie de ton fichier de production pour les premiers essais.

## Fichiers ignorés par Git

Le `.gitignore` exclut notamment :

- `app_config.json`;
- `*.xlsx` et `*.xlsm`;
- les fichiers temporaires Excel `~$*.xlsx` et `~$*.xlsm`;
- `.venv/` et les fichiers Python temporaires.

Cela évite de pousser par erreur un chemin OneDrive personnel ou un classeur de production dans le dépôt.
