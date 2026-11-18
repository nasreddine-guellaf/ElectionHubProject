# ADR 0001 — Socle local limité à la phase 1

Date : 18 novembre 2026. Statut : décision d'implémentation locale.

## Décisions

- Monorepo avec `backend/`, `database/seeds/`, `scripts/` et `docs/`.
  Les dossiers `frontend/` et `cloud/` seront créés avec leurs premiers composants utiles.
- Python 3.11, FastAPI et Pydantic pour une API typée et documentée ; SQLAlchemy 2.0
  synchrone et psycopg 3 pour PostgreSQL ; Alembic pour les migrations explicites.
  Le volume attendu ne justifie pas encore une couche asynchrone de base de données.
- PostgreSQL 16 local, compatible avec l'architecture transactionnelle cible RDS,
  sans création de ressource AWS. Port hôte 5433 pour limiter les conflits habituels.
- Deux fichiers de versions verrouillées : exécution et développement. Les dépendances
  de test ne sont pas installées dans l'image API. Les images de base restent sur un tag
  de série pour les correctifs ; une livraison cloud devra figer et vérifier leurs digests.
- Modèle minimal `polling_stations` : UUID, code unique, nom, nombre d'inscrits non négatif,
  horodatage serveur avec fuseau. La contrainte d'unicité crée l'index du code ; pas d'index
  redondant. Régions, élections et inscriptions par scrutin seront normalisées en phase 2.
  Le nombre d'inscrits actuel est uniquement une valeur fictive de démonstration.
- Alembic est la seule source de création du schéma : pas de `create_all` au démarrage.
  Compose attend la santé PostgreSQL puis la réussite de la migration avant de lancer l'API.
- Seed explicite, transactionnel et idempotent par code : aucune réinitialisation et aucun
  écrasement d'un bureau existant. Données fictives `DEMO-*`, sans CIN, téléphone ou résultats.
- API locale de lecture uniquement, sans authentification anticipée. Ports publiés sur
  `127.0.0.1`, mode de configuration limité à `local` et `test`. Ne pas exposer ce socle
  sur Internet. Le RBAC serveur sera introduit avant les opérations métier protégées.
- Tests contre PostgreSQL réel avec un schéma aléatoire par test et migrations réelles.
  Aucun remplacement SQLite. Le nettoyage supprime uniquement le schéma généré par le test.
- `/health` est une sonde de disponibilité : elle exige la migration attendue et une table
  métier accessible. Une panne SQL retourne 503 sans détail de connexion ni paramètres SQL.
- `.env` généré localement avec un secret aléatoire, exclu de Git et de l'image Docker.
  Le compte PostgreSQL d'amorçage est destiné au développement uniquement ; les comptes
  migration et application seront séparés et restreints pour le cloud.

## Références techniques consultées

- [Démarrage ordonné Compose](https://docs.docker.com/compose/how-tos/startup-order/) :
  attente de disponibilité et de fin des tâches d'initialisation.
- [Dialecte PostgreSQL SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html) :
  utilisation explicite de `postgresql+psycopg`.
- [FastAPI dans Docker](https://fastapi.tiangolo.com/deployment/docker/) : image construite
  depuis Python et commande de lancement sous forme exec.

## Limites acceptées

Aucun frontend, compte, OTP, dépôt de fichier, validation, publication, pipeline cloud
ou basculement dans ce jalon. Ces limites respectent la demande de commencer par la phase 1.
