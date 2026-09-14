# Développement Web V2 — React + FastAPI + SQLite

Le frontend React V2 peut être développé et validé sans attendre l'accès au SQL Server cible. Le navigateur ne connaît ni Excel ni SQL : il consomme uniquement FastAPI.

## Architecture locale de développement

```text
React / Vite :5173
       │ proxy /api + /health
       ▼
FastAPI :8000
       │
       ▼
resourceplanner_server.db
```

Le runtime d'exploitation utilise maintenant une variante plus simple : le build React est servi directement par FastAPI sur le même port. Voir `WEB_RUNTIME.md`.

## 0. Préparer l'environnement Web

La première fois :

```bat
Installer_Web.bat
```

Cela crée `.venv-web`, installe les dépendances serveur sans NiceGUI/Excel, installe les dépendances Node et produit aussi un build React de production.

## 1. Préparer le backend local pour Vite

Depuis la racine :

```bat
Lancer_Serveur.bat
```

Si `RESOURCEPLANNER_DATABASE_URL` n'est pas définie, le lanceur utilise :

```text
sqlite:///./resourceplanner_server.db
```

Dans ce mode local SQLite, il applique `alembic upgrade head` avant de démarrer FastAPI. Si une URL explicite est configurée, elle est conservée et aucune migration automatique n'est exécutée.

Le serveur répond par défaut à :

- `http://127.0.0.1:8000/health`;
- `http://127.0.0.1:8000/docs`.

`Lancer_Serveur.bat` est volontairement un mode API seul pour le développement. Il utilise `.venv-web`.

## 2. Charger les données de démonstration

Fermer le serveur puis lancer :

```bat
Charger_Donnees_Demo.bat
```

Le chargeur utilise maintenant le même environnement `.venv-web`. Il :

- cible uniquement `resourceplanner_server.db`;
- applique les migrations;
- refuse un moteur autre que SQLite;
- crée projets, ressources, disponibilités, WorkPackages, demandes, périodes, segments et quarts;
- replace les dates autour de la semaine courante;
- remplace seulement les données rattachées aux projets `DEMO-*`.

Après chargement, le chemin le plus simple pour tester l'application complète est :

```bat
Lancer_Web.bat
```

## 3. Développement React avec HMR

Pour modifier React avec Vite, garder `Lancer_Serveur.bat` ouvert puis, dans un deuxième terminal :

```bat
cd frontend
npm run dev
```

Ouvrir `http://127.0.0.1:5173`.

Vite relaie `/api` et `/health` vers `http://127.0.0.1:8000`, ce qui évite une politique CORS dédiée au développement.

## 4. Build de production

```bat
cd frontend
npm run build
```

Le build exécute TypeScript puis Vite et produit `frontend/dist`.

Pour tester exactement le runtime cible après le build :

```bat
cd ..
Lancer_Web.bat
```

FastAPI sert alors :

```text
http://127.0.0.1:8000/
  ├─ /             → React / Vite build
  ├─ /assets/*     → assets statiques
  ├─ /api/v1/*     → FastAPI
  └─ /health       → FastAPI / SQL
```

Aucun processus `vite preview` ou serveur Node n'est requis en exploitation.

## 5. API distante optionnelle

Le frontend conserve `VITE_API_BASE_URL` pour des scénarios de développement/intégration particuliers. Le runtime cible normal n'en a pas besoin car React et FastAPI sont same-origin.

## 6. Validation

GitHub Actions :

1. exécute les tests Python;
2. construit React avec Node 22;
3. exécute `tools/check_web_runtime.py` contre le vrai `frontend/dist`;
4. vérifie que le serveur Web/SQL reste isolé du runtime NiceGUI/Excel.

Le smoke complet peut aussi être lancé localement après un build :

```bat
.venv-web\Scripts\python.exe tools\check_web_runtime.py
```

## 7. Autorité métier

Même en développement React :

- FastAPI reste la frontière de mutation;
- le moteur Python reste autoritaire pour planification/capacité;
- React ne doit pas recopier les règles de non-double-comptage;
- Acumatica n'est jamais appelé directement par le navigateur.

Refs : #55, #162, #187, #189, #192, #198, #203, #208, #211, #212.
