# Rapport de vérification — Phase 1

Vérifications exécutées le **18 novembre 2026**, sur Windows, depuis le workspace
ElectionHub initialement vide. Aucun compte cloud utilisé, aucun déploiement distant.

## A. Implémentation

- API FastAPI avec fabrique d'application, sessions SQLAlchemy par requête, sonde
  `/health`, liste paginée et lecture individuelle des bureaux de vote.
- Modèle PostgreSQL avec UUID, code unique, champs obligatoires, compteur non négatif,
  noms non vides et horodatage serveur.
- Migration Alembic explicite, réversible, vérifiée contre les métadonnées du modèle.
- Trois bureaux synthétiques JSON et chargement idempotent conservant les données existantes.
- Compose avec PostgreSQL, tâche de migration et API non root ; ports liés à localhost.
- Configuration Pydantic, secret local aléatoire exclu de Git et du contexte Docker.
- Environnement virtuel, versions de dépendances verrouillées, 24 tests automatisés.
- README PowerShell et WSL, transcription V2, sept flux et décisions locales documentés.
- Dépôt Git initialisé sur `main`, sans commit ni publication distante.

Fichiers principaux : `backend/app/`, `backend/alembic/`, `backend/tests/`,
`backend/pyproject.toml`, `backend/requirements*.lock`, `backend/Dockerfile`,
`database/seeds/polling_stations.json`, `docker-compose.yml`, `scripts/init_env.py`,
`.env.example`, `.gitignore`, `.dockerignore`, `README.md` et `docs/`.

## B. Commandes et résultats observés

Environnement : Python hôte 3.11.9, Docker Desktop avec conteneurs Linux,
PostgreSQL **16.16**, FastAPI 0.165.0, SQLAlchemy 2.0.58, psycopg 3.3.9,
Alembic 1.20.1. Versions exactes dans les fichiers de dépendances verrouillées.

Les commandes Python ci-dessous ont utilisé `.venv/Scripts/python.exe`, depuis
`backend/` pour l'application, Alembic et pytest. Compose s'exécute à la racine.

| Vérification exécutée | Résultat |
|---|---|
| `python scripts/init_env.py` (racine), puis seconde exécution | Fichier généré, puis fichier existant conservé sans afficher le secret |
| `docker compose config --quiet` | Configuration valide, code 0 |
| `docker compose up -d --wait db` | Base démarrée et saine |
| `python -m alembic upgrade head` | Migration initiale appliquée, code 0 |
| `python -m alembic check` | Aucune différence de schéma détectée |
| `python -m app.seed` répété après correction | Aucun ajout après premier chargement ; total conservé à 3 |
| `python -m pytest -q` | **24 tests réussis**, 1 avertissement, 1,98 s |
| `python -m ruff check .` | Tous les contrôles passent |
| `python -m ruff format --check .` | 14 fichiers conformes |
| Ruff sur `scripts/` | Contrôle et format conformes, 1 fichier |
| `python -m compileall -q backend/app backend/alembic scripts` (racine) | Compilation réussie |
| `docker compose --progress plain up -d --build --wait` | Images construites ; migration terminée ; API et base saines |
| `docker compose exec api python -m app.seed` | 0 nouveau bureau, idempotence confirmée dans le conteneur |
| `docker compose exec api alembic check` | Aucune différence de schéma détectée dans le conteneur |
| HTTP GET `/health` via PowerShell | 200, base disponible, migration `0001_polling_stations`, environnement `local` |
| HTTP GET `/api/v1/polling-stations` via PowerShell | 200, total 3, marqueur `synthetic` |
| HTTP GET `/docs` via PowerShell | 200 |
| Comparaison des noms HTTP UTF-8 avec le fichier JSON via Python | Correspondance exacte, accents préservés |
| SQL direct dans PostgreSQL | Codes DEMO-BV-001 à 003 ; 600, 450 et 720 inscrits fictifs |
| Comptage des schémas `test_%` après pytest | 0 schéma restant |
| `docker compose exec api id -u` | 1000 : processus non root |
| `git check-ignore .env .venv .local` | Les trois chemins sont exclus |

Couverture des tests : première insertion et répétition du seed, conservation d'un bureau
modifié, listes vides, pagination et détail, UUID incorrect et bureau absent, indisponibilité
SQL sans fuite de détails, table absente, version de migration incorrecte, unicité et
contraintes PostgreSQL, migration upgrade/downgrade/upgrade, configuration locale et
mot de passe avec caractères réservés. Chaque test d'intégration utilise son propre
schéma PostgreSQL ; les données de démonstration restent intactes.

## Corrections et limites observées

- Docker Desktop était arrêté au départ. Il a été démarré pour exécuter les vérifications.
- Le bac à sable empêchait initialement l'accès au cache utilisateur et à PyPI. Le cache
  a été déplacé dans `.local/` ; les téléchargements et accès Docker ont ensuite été
  exécutés avec l'autorisation de l'environnement.
- Première exécution pytest : 22 succès et 1 échec. `rowcount` de psycopg valait -1
  pour l'insertion utilisée. Correction par `INSERT ... RETURNING id`, puis ajout d'un
  test du premier chargement : 24 succès dans la dernière exécution.
- L'avertissement Alembic sur le séparateur de chemins a été corrigé par `path_separator=os`.
- L'avertissement restant concerne la dépréciation de l'usage de `httpx` par le TestClient
  Starlette installé. Il n'est pas masqué ; les tests passent. Prévoir la migration du
  client de test lors de la prochaine mise à jour des dépendances.
- Windows PowerShell 5.1 affiche mal certains accents JSON. Une lecture HTTP avec Python
  confirme que les octets UTF-8 et les noms enregistrés sont corrects.
- Git a détecté la différence de propriétaire entre le bac à sable et le compte Windows.
  Les vérifications Git ont utilisé une exception `safe.directory` limitée à chaque
  commande et à ce dossier ; aucune configuration globale n'a été modifiée.
- Les instructions d'un environnement Python natif WSL sont documentées mais non exécutées.
  L'image API Linux a en revanche été construite et exécutée via Docker Desktop.

## C. Fonctionnement vérifié

Le parcours local **PostgreSQL → migration → données fictives → FastAPI → client HTTP**
fonctionne. L'API et la base sont laissées démarrées sur les ports locaux 8000 et 5433.
La tâche de migration est arrêtée avec succès (code 0), ce qui est son état normal.

## D. Travail restant hors phase 1

Pas encore de frontend, comptes, RBAC, OTP, PV, incidents, validation humaine, publication,
BigQuery, Looker Studio ou intégration multi-cloud. Aucune preuve de fonctionnement
des sept flux cloud, de TLS inter-cloud ou de basculement automatique.

## E. Prochain jalon recommandé

Phase 2 uniquement après revue de ce socle : normaliser élections, régions, candidats,
affectations, rapports et révisions ; définir les transitions autorisées et les équations
de cohérence configurables ; tester les contraintes et l'absence de double comptage.
Prérequis : préciser les règles métier des rapports et les portées d'affectation.
Critère attendu : API métier et migrations vérifiées sur PostgreSQL, sans approbation
automatique et sans intégration cloud prématurée.
