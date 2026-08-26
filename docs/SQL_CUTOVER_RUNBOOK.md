# Runbook — cutover net Excel → SQL

Ce document décrit le basculement one-shot de RessourcePlanner V1 (Excel) vers la base SQL autoritaire.

## Principes

- aucune période hybride Excel/SQL;
- aucune double écriture;
- aucun fallback silencieux vers Excel;
- le classeur V1 est gelé avant l'import final;
- l'import final exige une base RessourcePlanner vide;
- les quarts verrouillés sont importés tels quels, sans rebuild du moteur;
- si le préflight ou la réconciliation échoue, SQL n'est pas déclaré autoritaire;
- aucune correction artisanale de la base importée : corriger la source/l'importeur, recréer la base et réimporter.

## 1. Préparer le poste de migration

Installer les dépendances du dépôt :

```bat
python -m pip install -r requirements.txt
```

Le dry-run utilise `openpyxl` en lecture seule. Microsoft Excel n'est pas nécessaire pour lire le classeur gelé.

## 2. Dry-run avant le jour du cutover

Exécuter contre une copie récente du classeur :

```bat
python tools\cutover_excel_to_sql.py --workbook "C:\chemin\RessourcePlanner.xlsm" --report "C:\temp\cutover_preflight.json"
```

Sans `--apply`, aucune connexion SQL n'est nécessaire et aucune écriture SQL n'est effectuée.

Le rapport contient notamment :

- SHA-256 du classeur;
- commit Git courant si disponible;
- nombres de projets, WorkPackages, ressources, disponibilités, demandes, historiques, segments et quarts;
- nombre de quarts verrouillés;
- sommes des heures prévues et des heures de quarts;
- diagnostics bloquants et avertissements;
- statut `ready_for_apply`.

Un exit code `0` signifie que le préflight est prêt. Un exit code `2` signifie que les données sont bloquantes. Un exit code `3` signifie une erreur technique.

## 3. Corriger les anomalies avant le gel

Les anomalies bloquantes typiques sont :

- ID legacy dupliqué (`NoDemande`, `IDEffort`, `IDSegment`, `IDAllocation`, disponibilité);
- projet, demande, ressource ou segment référencé mais introuvable;
- dates/heures invalides;
- historique sans horodatage;
- lien `SourceEffortID` inconnu ou rattaché au mauvais projet;
- Quick Shift/ad hoc relié à une fausse demande;
- besoin `REQUEST` sans demande.

Relancer le dry-run après chaque correction jusqu'à `ready_for_apply=true`.

## 4. Geler la V1

Au moment du cutover final :

1. arrêter l'utilisation de RessourcePlanner V1;
2. fermer/terminer les modifications Excel en cours;
3. faire une copie finale du classeur;
4. conserver le commit Git de la V1 gelée;
5. exécuter un dernier dry-run sur **cette copie exacte**;
6. archiver le classeur et son rapport JSON.

Exemple d'archive :

```text
archive/cutover/
  RessourcePlanner_final_2026-xx-xx.xlsm
  cutover_preflight_2026-xx-xx.json
  version.txt
```

Ne jamais modifier cette copie après le dry-run final.

## 5. Préparer SQL Server

La base de destination doit être dédiée à RessourcePlanner. Le compte utilisé pour le cutover doit pouvoir :

- créer/modifier le schéma pour Alembic;
- lire/écrire les tables RessourcePlanner;
- exécuter une transaction complète.

Configurer l'URL SQLAlchemy dans une variable d'environnement. Ne jamais inscrire le mot de passe dans Git :

```bat
set RESOURCEPLANNER_DATABASE_URL=<URL SQLAlchemy SQL Server>
```

Le driver SQL Server/ODBC exact sera validé sur le serveur cible avant le cutover réel.

## 6. Import final

```bat
python tools\cutover_excel_to_sql.py ^
  --workbook "C:\archive\RessourcePlanner_final.xlsm" ^
  --report "C:\archive\cutover_apply.json" ^
  --apply
```

Le CLI effectue dans cet ordre :

1. SHA-256 du classeur;
2. lecture read-only et préflight final;
3. refus immédiat si le préflight n'est pas propre;
4. `alembic upgrade head` explicite;
5. ouverture d'une transaction SQL;
6. vérification que les tables métier sont vides;
7. import complet dans l'ordre des dépendances;
8. réconciliation des volumes/heures/verrous;
9. nouveau SHA-256 du classeur;
10. commit uniquement si tout est cohérent.

Aucun rebuild du planning n'est exécuté pendant cet import.

## 7. Critères d'acceptation

Le rapport final doit confirmer au minimum :

- mêmes nombres de demandes, segments, quarts et quarts verrouillés;
- mêmes heures prévues de WorkPackages/segments;
- mêmes heures totales de quarts et heures verrouillées;
- 0 shift orphelin;
- 0 segment sans projet;
- 0 référence demande/ressource inconnue;
- 0 Quick Shift avec fausse demande;
- 0 identifiant legacy dupliqué;
- SHA-256 du classeur inchangé pendant l'opération.

## 8. Échec / rollback

Si l'import de données échoue dans la transaction, aucune donnée métier partielle ne doit être conservée.

Alembic peut avoir créé le schéma avant l'import. Ce n'est pas considéré comme un cutover partiel tant que les tables métier sont vides. Pour le cutover final, la pratique recommandée reste :

1. supprimer/recréer la base de destination si nécessaire;
2. corriger la cause;
3. relancer Alembic + l'import depuis le même classeur gelé;
4. générer un nouveau rapport.

Ne pas éditer directement les lignes SQL pour faire « balancer » le rapport.

## 9. Déclarer SQL autoritaire

SQL devient autoritaire seulement après :

- import `--apply` réussi;
- rapport de réconciliation acceptable;
- test fonctionnel des workflows critiques;
- validation explicite du nouveau runtime SQL.

À partir de ce moment, le classeur gelé reste une archive/porte de retour d'urgence. Il ne doit plus recevoir de modifications normales.
