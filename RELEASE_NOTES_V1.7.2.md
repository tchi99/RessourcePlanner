# RessourcePlanner V1.7.2

Correctif de compatibilité pour la distribution V1.7 sous les versions récentes de NiceGUI.

## Correctif principal

- corrige l'erreur de démarrage `ui.add_head_html ... global scope while using ui.page`;
- les styles et éléments HTML communs à l'application sont maintenant explicitement enregistrés comme ressources partagées NiceGUI;
- ajoute un test de démarrage en CI avant de générer l'exécutable Windows afin que ce type de régression soit détecté avant publication.

## Inclus

Cette version contient également toutes les fonctionnalités et optimisations de V1.7.1 : planning opérationnel interactif, workflow d'approbation, segments/allocations, ressources et compétences, tri manuel local, cache des disponibilités et écritures Excel groupées.

## Prérequis

- Windows 10 ou Windows 11 64 bits;
- Microsoft Excel de bureau installé;
- pour OneDrive/SharePoint, le classeur doit être synchronisé localement;
- Python n'est pas requis pour utiliser l'exécutable.

## Sécurité Windows

L'exécutable n'est pas encore signé avec un certificat de signature de code. Windows SmartScreen peut afficher un avertissement `Éditeur inconnu` au premier lancement.
