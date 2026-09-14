# Inventaire de cutover V1 → SQL

Ce document suit la **fin du runtime NiceGUI/Excel**, pas la migration des données.

L'import one-shot Excel → SQL est déjà livré par #158 / PR #161 avec `tools/cutover_excel_to_sql.py` et `docs/SQL_CUTOVER_RUNBOOK.md`. Il ne doit pas être réécrit dans ce chantier.

## État de départ

Le produit possède maintenant deux chemins clairement distincts.

### Runtime Web/SQL cible

```text
React
  ↓ REST
FastAPI
  ↓
ApplicationFacade / services / moteur pur
  ↓
repositories SQLAlchemy
  ↓
SQLite dev/test aujourd'hui
SQL Server cible
```

Les packages canoniques protégés sont :

- `app/domain`;
- `app/application`;
- `app/infrastructure/sql`;
- `app/infrastructure/acumatica`;
- `app/server`.

Ils ne doivent pas acquérir de nouvelle dépendance vers NiceGUI, xlwings, openpyxl ou les modules V1 historiques.

L'inventaire initial a détecté **une dette déjà existante et explicitement baselinée** : `app/application/runtime_services.py` construit encore les services NiceGUI V1 avec les adapters `app.infrastructure.excel`. Ce bridge est utilisé uniquement par la composition/UI historique et doit disparaître avant le retrait final de V1. Le garde-fou fonctionne comme un *ratchet* : cette dette précise reste visible, mais toute nouvelle violation fait échouer la CI.

### Runtime V1 encore actif

Le lanceur historique reste :

```text
Lancer_Application.bat
  ↓
main.py
  ├─ NiceGUI
  ├─ app.runtime_composition
  ├─ ExcelRepository
  └─ PlannerUI
       ↓
       classeur Excel
```

`app/runtime_composition.py` rend explicite la dette de transition : compatibilités, modules V1 versionnés, pages NiceGUI et anciennes communications sont encore installés pour l'application historique.

`requirements.txt` mélange encore les dépendances du nouveau serveur avec `nicegui`, `xlwings` et `openpyxl`. Cette séparation est l'objet de la tranche 6B.

## Inventaire automatique

Exécuter :

```bat
python tools\cutover_inventory.py
```

Pour le rapport JSON :

```bat
python tools\cutover_inventory.py --format json
```

Pour le garde-fou CI :

```bat
python tools\cutover_inventory.py --check-boundaries
```

La commande distingue :

- la dette de frontière **connue** au début du cutover;
- les violations **inattendues**.

Elle retourne un code d'échec uniquement pour une régression au-delà de la baseline explicite. Une baseline ne constitue pas une permission architecturale : elle doit rétrécir au fur et à mesure du cutover et ne doit jamais être élargie pour faire passer une PR.

L'inventaire expose séparément :

- les entrypoints V1 encore présents;
- les dépendances runtime historiques;
- les modules `v*.py`;
- les modules `*_compat.py`;
- les modules UI NiceGUI;
- les modules/adapters Excel;
- le nombre et les catégories des étapes de `runtime_composition`;
- l'outil de migration one-shot, qui demeure volontairement disponible jusqu'au cutover réel;
- la dette de frontière connue et les nouvelles violations éventuelles.

## Ordre de retrait recommandé

### 6A — frontières et inventaire

Empêcher toute nouvelle dépendance Web/SQL → V1 et mesurer la dette existante. Cette étape ne supprime aucun comportement utilisateur.

### 6B — dépendances séparées

Créer un ensemble de dépendances serveur minimal sans NiceGUI/xlwings/openpyxl et le valider en CI. Le runtime V1 peut conserver temporairement son propre requirements explicite.

### 6C — parité utile, pas parité historique aveugle

Comparer uniquement les fonctions NiceGUI encore réellement nécessaires au jour du cutover avec les surfaces React/FastAPI actuelles. Chaque manque sera classé :

- **migrer** : nécessaire à l'exploitation;
- **supprimer** : comportement historique devenu inutile;
- **reporter/remplacer** : fonctionnalité couverte par une architecture cible différente.

Les anciennes communications Outlook/Thunderbird ne doivent notamment pas être recopiées automatiquement dans React si #40/M365 constitue la cible retenue.

Le bridge `app/application/runtime_services.py` fait partie de cette dette : il pourra être déplacé/supprimé lorsque ses derniers appelants NiceGUI ne seront plus nécessaires.

### 6D — runtime Web autonome

Le lancement normal devra démarrer le backend FastAPI et servir/utiliser le frontend React sans `main.py`, `PlannerUI`, `ExcelRepository` ou `runtime_composition`.

L'ancien lanceur pourra être conservé temporairement sous un nom explicitement legacy pendant la transition.

### 6E — cutover réel

Cette étape attend la validation SQL Server #162 :

1. geler la V1;
2. archiver le classeur final;
3. exécuter l'import #158/#161;
4. réconcilier le rapport;
5. démarrer le runtime Web sur SQL Server;
6. effectuer les smoke tests lecture/mutation;
7. déclarer SQL autoritaire;
8. conserver Excel uniquement pour import/export/archive;
9. supprimer enfin le runtime V1 et les dépendances devenues inutiles.

## Règles non négociables

- aucune double écriture Excel + SQL;
- aucun fallback silencieux vers Excel après le cutover;
- aucun secret dans les fichiers versionnés;
- FastAPI reste la frontière de mutation métier;
- React n'implémente pas les règles de capacité, approbation ou non-double-comptage;
- les outils one-shot de migration peuvent conserver une dépendance Excel isolée sans que cette dépendance appartienne au runtime serveur;
- la baseline de dette de frontière doit seulement diminuer, jamais augmenter pour contourner le garde-fou.

Refs : #15 #55 #158 #161 #162 #208
