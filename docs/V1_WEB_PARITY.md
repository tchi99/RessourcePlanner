# Parité utile V1 → Web/SQL

Ce document répond à une seule question : **qu'est-ce qui doit réellement exister dans React/FastAPI avant de pouvoir retirer le runtime NiceGUI/Excel?**

Il ne cherche pas à reproduire écran pour écran la V1. La règle de décision est :

- **MIGRER — bloque le cutover** : capacité opérationnelle nécessaire après le jour du basculement;
- **COUVERT** : capacité déjà disponible dans React/FastAPI/SQL;
- **SUPPRIMER AU CUTOVER** : fonction uniquement utile parce qu'Excel est aujourd'hui le stockage autoritaire;
- **REPORTER / REMPLACER** : utile, mais la cible V2 est différente et elle ne doit pas être recopiée telle quelle.

---

## Résumé exécutif

La majorité du flux métier est déjà couverte par React V2 :

- planning opérationnel;
- édition de quarts;
- Quick Shift;
- moyen terme / WorkPackages;
- demandes, périodes, alternatives et approbations;
- portefeuille Projets + Acumatica Phase 1.

Deux écarts restent de vrais bloqueurs du retrait de NiceGUI :

1. **administration des ressources, compétences et disponibilités — #211**;
2. **édition/assignation des ResourceRequirements (segments) depuis React — #212**.

Les autres surfaces V1 ne doivent pas retarder le cutover SQL.

---

## Matrice de décision

| Surface / capacité V1 | État V2 | Décision | Justification |
|---|---|---|---|
| Planning opérationnel hebdomadaire | React + FastAPI livrés | **COUVERT** | Snapshot SQL, filtres, charge ferme/potentielle, édition de quart |
| Quick Shift | React + FastAPI livrés | **COUVERT** | Chemin ad hoc sans fausse demande |
| Moyen terme / efforts | React WorkPackages livré | **COUVERT** | WorkPackages, capacité, mutations, demandes liées |
| Demandes / approbations | React + FastAPI livrés | **COUVERT** | Création, modification, périodes, alternatives, workflow |
| Projets | React + sync Acumatica Phase 1 | **COUVERT** | SQL local opérationnel + frontière ERP |
| Tableau de bord V1 | Données déjà exposées ailleurs | **SUPPRIMER COMME BLOQUEUR** | Agrégat de KPI; utile éventuellement plus tard, mais aucune mutation exclusive |
| Segments : liste / détail | API read déjà présente | **MIGRER — #212** | React ne permet pas encore de travailler directement avec le besoin ressource |
| Segments : créer / modifier / annuler / assigner | API command déjà présente | **MIGRER — #212** | Commandes backend prêtes, surface React manquante |
| Recommandation de ressource V1 | Pas de surface React dédiée | **REPORTER** | Aide à la décision, pas nécessaire pour préserver la capacité d'opérer; moteur/règles pourront être réexposés plus tard |
| Ressources : créer / modifier / activer / désactiver | SQL existe; lecture API seulement | **MIGRER — #211** | Nécessaire pour administrer l'équipe après cutover |
| Classe / compétences / note / ordre ressource | SQL existe; lecture API seulement | **MIGRER — #211** | Influence le planning, le tri et la capacité opérationnelle |
| Horaire standard ressource | SQL `ResourceAvailabilityRule` existe; pas d'API de mutation | **MIGRER — #211** | Le calcul de capacité dépend directement de ces règles |
| Vacances / absences | SQL supporte les règles; pas d'admin Web | **MIGRER — #211** | Nécessaire pour maintenir une capacité fiable après cutover |
| Jours fériés globaux | SQL supporte `resource_id=NULL` pour `Jour férié` | **MIGRER — #211** | Nécessaire à la capacité, mais peut partager la même surface Disponibilités |
| Ordre manuel / préférences locales V1 | `Resource.sort_order` existe | **MIGRER LE MINIMUM — #211** | Conserver l'ordre serveur; ne pas reproduire les préférences Excel/locales inutiles |
| Rebuild planning explicite | Route FastAPI `/planning/rebuild` existe | **REPORTER / SUPPORT** | Pas un manque de domaine; ajouter un bouton admin seulement si nécessaire |
| Données Excel génériques | Spécifique au classeur | **SUPPRIMER AU CUTOVER** | Une grille SQL générique serait un anti-pattern et contournerait les services métier |
| Paramètres chemin classeur / OneDrive | Spécifique au runtime V1 | **SUPPRIMER AU CUTOVER** | SQL devient autoritaire; aucun fichier partagé à configurer |
| Auto-refresh signature Excel | Spécifique à Excel | **SUPPRIMER AU CUTOVER** | Les lectures Web passent par API/SQL |
| Communications Outlook / Thunderbird | Runtime historique | **REPORTER / REMPLACER** | La cible est #40 / M365 derrière une frontière remplaçable |
| Communications React placeholder | Non livré | **NON BLOQUANT** | Ne doit pas forcer la conservation d'Excel/NiceGUI |
| Validation moteur pur / diagnostics V1 | Backend/tests disponibles | **SUPPORT** | Garder les diagnostics côté backend/CI plutôt que reproduire des patchs UI |

---

## Bloqueur 1 — Administration Ressources & Disponibilités — #211

### Déjà présent

SQL possède déjà :

- `Resource.id` stable;
- nom, courriel, classe, compétences, note;
- `active`;
- `sort_order`;
- `ResourceAvailabilityRule`;
- horaire standard;
- fenêtres de dates;
- jours de semaine;
- heures début/fin;
- vacances/absences;
- jours fériés globaux.

Le moteur moyen terme consomme déjà ces règles pour calculer la capacité. Il ne manque donc pas un nouveau modèle métier : il manque **l'administration Web**.

### À livrer avant cutover

Backend :

- create/update/deactivate Resource;
- lecture détaillée des availability rules;
- create/update/delete/deactivate availability rule;
- validation déterministe des types, dates et heures;
- protection des noms/identités stables;
- aucune suppression physique opportuniste d'une ressource déjà référencée.

React :

- page Administration / Ressources;
- création et modification profil;
- actif/inactif;
- classe, compétences, note, ordre;
- horaire standard;
- absences/vacances;
- jours fériés globaux;
- états loading/error/empty.

### À ne pas recopier

- écriture directe dans une feuille `RessourcesMO`;
- édition générique de `Disponibilites` comme tableau Excel;
- préférences locales de tri qui contournent `sort_order` serveur.

---

## Bloqueur 2 — Segments / ResourceRequirements dans React — #212

### Déjà présent

FastAPI expose déjà :

- `GET /api/v1/segments`;
- `GET /api/v1/segments/{segment_id}`;
- `POST /api/v1/segments`;
- `PATCH /api/v1/segments/{segment_id}`;
- `POST /api/v1/segments/{segment_id}/cancel`;
- `POST /api/v1/segments/{segment_id}/assign`;
- création / édition / release / suppression d'allocations;
- édition de quarts et Quick Shift.

La dette n'est donc pas dans le domaine ni dans la persistance : elle est principalement **frontend**.

### À livrer avant cutover

- ouvrir le ResourceRequirement lié depuis le planning opérationnel;
- afficher les segments d'une demande dans l'espace Demandes;
- créer un segment lorsque le workflow l'exige;
- modifier fenêtre, heures, compétence, type de planification, priorité, hors horaire et confirmation;
- assigner/réassigner une ressource;
- annuler un segment;
- recharger les données autoritaires après mutation;
- conserver FastAPI comme autorité de validation.

Une page `Segments` autonome n'est **pas obligatoire**. L'intégration aux écrans Planning + Demandes est préférable si elle couvre les mêmes opérations avec moins de navigation.

---

## Capacités V1 volontairement non bloquantes

### Dashboard

Le Dashboard V1 combine essentiellement des compteurs et une vue de charge. Le planning, le moyen terme et les demandes possèdent déjà ces informations sous une forme plus directement actionnable. Un dashboard V2 pourra revenir plus tard, mais il ne justifie pas de conserver NiceGUI.

### Données Excel

La grille d'édition générique des feuilles doit disparaître. Recréer une grille SQL générique permettrait de contourner les validations de domaine, les services applicatifs et l'audit. Chaque mutation nécessaire doit avoir une commande métier explicite.

### Paramètres Excel

Le chemin OneDrive, la connexion xlwings et la signature des feuilles disparaissent avec le cutover SQL. Leur absence en React est donc une **preuve de simplification**, pas un manque de parité.

### Communications

Les intégrations Outlook/Thunderbird du runtime V1 ne doivent pas être portées automatiquement. La cible reste #40/M365. Elles peuvent rester disponibles dans V1 pendant la transition sans bloquer le passage du cœur de planification à SQL/Web.

---

## Ordre recommandé après cette analyse

1. **#211 — Ressources & disponibilités Web** : bloqueur principal, car c'est une mutation opérationnelle sans équivalent Web aujourd'hui.
2. **#212 — Segments intégrés Planning/Demandes** : backend déjà prêt, principalement travail React.
3. **Runtime Web autonome** : servir/lancer React + FastAPI sans `main.py`.
4. Validation réelle SQL Server #162 lorsqu'elle devient possible.
5. Cutover #158/#161, puis retrait définitif du runtime V1.

Le Dashboard, les communications et les fonctions de recommandation peuvent avancer indépendamment après le cutover de base.

Refs : #40 #55 #158 #161 #162 #208 #209 #210 #211 #212
