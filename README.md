# ElectionHub — Domaine électoral local, phase 2

Plateforme académique de consultation et consolidation des résultats par bureau de vote.
**Aucun vote électronique. Données de démonstration entièrement fictives.**

Le socle FastAPI/PostgreSQL de phase 1 est conservé. La phase 2 ajoute les scrutins,
candidats, affectations, PV révisables, résultats structurés et contrôles métier.
Les nouvelles API sont **désactivées par défaut**, avec activation locale explicite par clé.
Aucune ressource AWS, Azure, GCP ou Cloudflare n'est déployée.

## Prérequis

- Docker Desktop démarré en mode conteneurs Linux (WSL 2 sous Windows), Compose v2.
- Python 3.11 et `pip` pour les commandes locales. `uv` est une alternative facultative.
- Accès réseau initial à Docker Hub et PyPI pour télécharger les dépendances.
- Ports locaux 5433 (PostgreSQL) et 8000 (API) disponibles.

PowerShell 7 est recommandé pour l'affichage Unicode. Windows PowerShell 5.1 peut
mal afficher les accents des réponses JSON avec `Invoke-RestMethod` ; les données
HTTP sont bien encodées en UTF-8 et s'affichent correctement dans le navigateur.

Le projet se trouve initialement dans `C:\Users\nasrn\OneDrive\Desktop\ElectionHub`.
Exécuter les premières commandes depuis cette racine. Aucune activation PowerShell
de l'environnement virtuel ni modification d'ExecutionPolicy n'est nécessaire.

## Démarrage Windows PowerShell

```powershell
python scripts/init_env.py
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec api python -m app.seed
docker compose exec api python -m app.seed_domain
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/polling-stations
```

`init_env.py` génère un mot de passe aléatoire dans `.env` et conserve un fichier existant.
Ne pas copier ni publier son contenu. `.env.example` est un modèle sans secret utilisable.
Compose démarre PostgreSQL, exécute `alembic upgrade head`, puis attend que l'API soit saine.
Le seed est volontairement une commande distincte ; l'exécuter à nouveau ne crée pas de doublon.

Ouvrir la [documentation interactive locale](http://127.0.0.1:8000/docs).
La réponse `/health` doit contenir `status: ok`, `database: ok`,
`schema_version: 0002_election_domain`. La liste doit contenir `total: 3` et
`data_kind: synthetic` après chargement initial.

Le seed métier ajoute un scrutin fictif, trois listes, trois références utilisateur,
trois affectations, un PV soumis et un brouillon renseigné. Il conserve les dossiers existants.
Le troisième bureau reste disponible pour un nouvel essai. Aucun résultat n'est approuvé.
Voir [l'activation et le parcours API phase 2](docs/api/phase-2.md).

## Développement et tests sous PowerShell

Depuis la racine, avec la base Compose démarrée :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic check
..\.venv\Scripts\python.exe -m app.seed
..\.venv\Scripts\python.exe -m app.seed_domain
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
Set-Location ..
```

Les tests créent et suppriment des schémas `test_<uuid>` dans le PostgreSQL local.
Ils nécessitent une base disponible et le droit de créer des schémas. Ils ne vident pas
les tables de démonstration et échouent si PostgreSQL n'est pas accessible.
Ne jamais les diriger vers une base de production.

Pour lancer l'API sur l'hôte avec rechargement automatique, arrêter seulement l'API Docker :

```powershell
docker compose stop api
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

La configuration charge `.env` à la racine, indépendamment du répertoire courant.
Les variables du processus ont priorité. Les migrations et le seed précèdent ce lancement.

## WSL / Linux

Activer l'intégration Docker Desktop de la distribution WSL. Préférer un clone dans
le système de fichiers Linux pour les performances ; ne pas réutiliser `.venv` Windows.
Sous Ubuntu, installer Python 3.11 et son module `venv` s'ils sont absents.

```bash
python3.11 scripts/init_env.py
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec api python -m app.seed
docker compose exec api python -m app.seed_domain
curl --fail http://127.0.0.1:8000/health
curl --fail 'http://127.0.0.1:8000/api/v1/polling-stations?limit=2&offset=0'
python3.11 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.lock
cd backend
../.venv/bin/python -m alembic check
../.venv/bin/python -m pytest -q
../.venv/bin/python -m ruff check .
../.venv/bin/python -m ruff format --check .
```

Ces instructions WSL sont fournies pour reproduction ; voir le rapport pour les
plateformes effectivement vérifiées. Aucune distribution WSL utilisateur n'est modifiée.

## Contrat API du jalon

| Route GET | Fonction | Réponses attendues |
|---|---|---|
| `/health` | Vérifie PostgreSQL et la migration | 200, ou 503 si indisponible / schéma incorrect |
| `/api/v1/polling-stations` | Liste ordonnée par code, `limit` 1–100, `offset` ≥ 0 | 200 ; 422 pour pagination invalide |
| `/api/v1/polling-stations/{uuid}` | Lit un bureau | 200 ; 404 absent ; 422 UUID invalide |
| `/docs` | Documentation OpenAPI interactive | 200 |

Ces lectures héritées de phase 1 ne nécessitent pas de compte et sont limitées à
l'environnement local fictif. Les nouvelles routes `/elections`, `/candidates`,
`/assignments`, `/reports` et leurs sous-routes exigent le mécanisme de développement.
L'authentification et les droits métier complets appartiennent à la phase 3.

## Organisation

```text
backend/
  app/                 Configuration, modèles, services métier, API, seeds
  alembic/             Migrations additives des phases 1 et 2
  tests/               Tests API, PostgreSQL, migrations et configuration
  pyproject.toml       Dépendances directes et outils
  requirements*.lock   Versions exactes résolues pour ce jalon
  Dockerfile           Image API sans dépendances de test, utilisateur non root
database/seeds/        Bureaux et domaine électoral fictifs JSON
scripts/              Initialisation, activation explicite, vérification HTTP
docs/architecture/    Transcription V2 et sept flux
docs/decisions/       Choix techniques et limites
docs/testing/         Résultats des vérifications exécutées
docker-compose.yml    PostgreSQL, migration à exécution unique, API
```

Le frontend React et les configurations cloud seront ajoutés aux phases concernées.
Le portail et le back-office cibles partageront **un seul Azure App Service**.

## Exploitation locale et dépannage

```powershell
docker compose ps -a
docker compose logs --tail 50 api migrate db
docker compose stop
docker compose start db api
```

- Si le moteur Docker est introuvable, démarrer Docker Desktop et attendre `docker info`.
- Une erreur 503 signifie que la base, la table ou la migration attendue manque.
  Exécuter `docker compose run --rm migrate`, puis contrôler `/health`.
- Si le port est occupé, modifier `POSTGRES_PORT` ou `API_PORT` dans `.env`, puis relancer
  Compose. Adapter les URL de vérification et la commande Uvicorn au port choisi.
- Le volume `postgres_data` persiste après `docker compose down`. Ne pas ajouter `-v`
  sauf volonté explicite d'effacer la base locale. Changer le mot de passe dans `.env`
  après initialisation ne change pas automatiquement celui du rôle PostgreSQL existant.
- Pour mettre à jour le code de l'API conteneurisée : `docker compose up -d --build --wait`.
- La version de migration et la constante de disponibilité doivent évoluer ensemble
  lors du prochain changement du schéma.

## Documents et prochain jalon

- [Architecture V2 et hypothèses](docs/architecture/v2.md)
- [Décisions du socle local](docs/decisions/0001-socle-local.md)
- [Vérifications de la phase 1](docs/testing/phase-1.md)
- [Conception phase 2](docs/decisions/0002-domaine-electoral.md)
- [Modèle relationnel](docs/database/phase-2.md)
- [API phase 2 et exemples](docs/api/phase-2.md)
- [Vérifications de la phase 2](docs/testing/phase-2.md)

**IMPLÉMENTÉ :** modèle relationnel, affectations, saisie complète des résultats,
transition DRAFT → SUBMITTED, corrections traçables, protection contre doublons et conflits.
**TESTÉ :** PostgreSQL réel, migrations réversibles et préservation du référentiel,
API métier, erreurs, concurrence et parcours HTTP local (voir rapport pour les résultats).
**PLANIFIÉ :** authentification et RBAC en phase 3, validation humaine autorisée,
documents S3/Lambda, analytics, publication et interconnexions cloud.

Pour vérifier les routes activées sans modifier `.env`, après seed et depuis la racine :

```powershell
.\.venv\Scripts\python.exe scripts/smoke_phase2.py
```

Ce script lance Uvicorn sur un port local éphémère avec une clé temporaire, vérifie
les lectures protégées et le CRUD d'un scrutin fictif temporaire, puis supprime ce scrutin
et arrête le serveur. Sous WSL : `.venv/bin/python scripts/smoke_phase2.py`.

Prochain jalon : comptes authentifiés, hachage des mots de passe, RBAC côté serveur,
portées d'affectation et décisions humaines auditées. Ne pas exposer le mécanisme de
développement comme authentification de production.
