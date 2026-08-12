# RessourcePlanner V1.7

Première version Windows distribuable de RessourcePlanner.

Le fichier `RessourcePlanner-V1.7.1-Windows-x64.exe` contient l'application et son environnement Python : **Python n'a pas besoin d'être installé sur le poste utilisateur**.

## Inclus dans cette version

- planification opérationnelle interactive avec déplacement des allocations;
- demandes et workflow d'approbation;
- segments et allocations de main-d'œuvre;
- classes de ressources et compétences;
- recommandations d'affectation;
- disponibilité, vacances et jours fériés;
- tri des ressources par disponibilité, ordre alphabétique ou ordre manuel local;
- préférences utilisateur locales non partagées dans Excel;
- optimisation des écritures/sauvegardes Excel de la V1.7.1;
- conservation du défilement du planning et section d'approbation réductible.

## Prérequis

- Windows 10 ou Windows 11 64 bits;
- Microsoft Excel de bureau installé (l'application utilise Excel via `xlwings`);
- pour un classeur partagé OneDrive/SharePoint, le fichier doit être synchronisé localement sur le PC;
- le moteur natif NiceGUI utilise les composants WebView/.NET normalement présents sur un poste Windows standard.

## Première utilisation

1. Télécharger l'exécutable et le placer dans un dossier où l'utilisateur possède les droits d'écriture.
2. Double-cliquer sur l'exécutable.
3. Dans **Paramètres**, sélectionner le classeur Excel local/synchronisé utilisé comme source.
4. L'application crée à côté de l'exécutable ses fichiers locaux `app_config.json` et `user_preferences.json` au besoin.

Ces fichiers locaux ne doivent pas être partagés dans GitHub. `user_preferences.json` peut notamment contenir des noms de ressources puisqu'il conserve l'ordre manuel propre à l'utilisateur.

## Sécurité Windows

Cette première distribution n'est pas signée avec un certificat de signature de code. Windows SmartScreen peut donc afficher un avertissement **Éditeur inconnu** au premier lancement. Une signature de code pourra être ajoutée dans une version ultérieure.
