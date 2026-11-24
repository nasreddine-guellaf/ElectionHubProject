# ElectionHub — Phase 5 en cours : stockage documentaire

Plateforme académique de consultation et consolidation des résultats par bureau de vote.
**Aucun vote électronique. Données de démonstration entièrement fictives.**

Le socle FastAPI/PostgreSQL, le domaine électoral, les sessions par rôle et l'application
React unique sont opérationnels. La première tranche de phase 5 ajoute les pièces privées,
un stockage local testable et un adaptateur S3 configurable. Les API métier exigent une
**session Bearer**. Le compte AWS A héberge le bucket S3 de démonstration et la base
PostgreSQL privée, qualifiée depuis un runner temporaire. L'API de secours EC2 est
accessible pour la recette via SSM. Le portail reste local.

## Prérequis

- Docker Desktop démarré en mode conteneurs Linux (WSL 2 sous Windows), Compose v2.
- Python 3.11 et `pip` pour les commandes locales. `uv` est une alternative facultative.
- Accès réseau initial à Docker Hub et PyPI pour télécharger les dépendances.
- Ports locaux 5433 (PostgreSQL), 8000 (API) et 3000 (application web) disponibles.

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

Ouvrir [l'application web locale](http://127.0.0.1:3000). La documentation interactive
de l'API reste disponible sur [le port 8000](http://127.0.0.1:8000/docs).
La réponse `/health` doit contenir `status: ok`, `database: ok`,
`schema_version: 0005_incidents`. La liste doit contenir `total: 3` et
`data_kind: synthetic` après chargement initial.

Le seed métier ajoute un scrutin fictif, trois listes, trois références utilisateur,
trois affectations, un PV soumis et un brouillon renseigné. Il conserve les dossiers existants.
Le troisième bureau reste disponible pour un nouvel essai. Aucun résultat n'est approuvé.
Voir [les comptes, permissions et parcours API phase 3](docs/api/phase-3.md).
Préparer les comptes sur l'hôte avec les commandes suivantes avant de se connecter.

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
..\.venv\Scripts\python.exe -m app.bootstrap_auth
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
Set-Location ..
```

Le bootstrap crée `demo-agent`, `demo-admin` et `demo-validator`, avec des mots de passe
aléatoires dans `.local/demo-credentials.json` (ignoré par Git et Docker). Il ne réinitialise
jamais un compte existant. Ce fichier contient les secrets initiaux : ne pas le partager.
Se connecter par `POST /api/v1/auth/login`, puis utiliser le jeton dans **Authorize** sur
`/docs`, ou suivre [l'exemple PowerShell](docs/api/phase-3.md#connexion-et-déconnexion-powershell).
Le citoyen `DEMO-CIN-0001` est fictif ; son OTP est **désactivé par défaut** et ne passe
que par un simulateur SMS local lorsqu'il est activé explicitement.

Le conteneur `web` sert le build React avec Nginx sur le port 3000 et transmet `/api/*`
au backend. Les liens profonds sont pris en charge, le système de fichiers est en lecture
seule et des en-têtes de sécurité encadrent le navigateur. Voir le
[guide frontend phase 4](docs/api/phase-4.md).

### PostgreSQL local et cible RDS

Le développement local conserve `POSTGRES_SSLMODE=disable`. Une cible RDS ou
`APP_ENV=cloud` exige `POSTGRES_SSLMODE=verify-full` et `POSTGRES_SSLROOTCERT` vers un
bundle CA valide. SQLAlchemy utilise un pool borné configurable ; les valeurs par défaut
sont 5 connexions persistantes et 5 connexions de débordement au maximum par processus.
Voir la [préparation backend AWS-4A](docs/infrastructure/aws-4a-backend-rds.md) et le
[plan de déploiement privé RDS AWS-4B](docs/infrastructure/aws-4b-rds-plan.md).

Pour développer l'interface avec rechargement automatique, laisser l'API sur le port 8000 :

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
npm.cmd test
npm.cmd run build
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
..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
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
curl --fail http://127.0.0.1:3000/
python3.11 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.lock
cd backend
../.venv/bin/python -m alembic check
../.venv/bin/python -m app.bootstrap_auth
../.venv/bin/python -m pytest -q
../.venv/bin/python -m ruff check .
../.venv/bin/python -m ruff format --check .
cd ../frontend
npm install
npm test
npm run build
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
`/assignments`, `/reports` et leurs sous-routes exigent une session et un rôle autorisé.
ADMIN gère les référentiels et comptes ; AGENT saisit ses PV affectés ; VALIDATOR examine
et décide. ADMIN ne peut ni soumettre ni approuver un PV. Le citoyen authentifié accède
à son bureau via une route dédiée. Voir la [matrice complète](docs/api/phase-3.md#matrice-des-droits).

## Organisation

```text
backend/
  app/                 Configuration, modèles, services métier, API, seeds
  alembic/             Migrations additives jusqu'aux documents et incidents de phase 5
  tests/               Tests API, PostgreSQL, migrations et configuration
  pyproject.toml       Dépendances directes et outils
  requirements*.lock   Versions exactes résolues pour ce jalon
  Dockerfile           Image API sans dépendances de test, utilisateur non root
frontend/              Application React unique, tests fonctionnels et image Nginx
database/seeds/        Bureaux et domaine électoral fictifs JSON
scripts/              Initialisation, simulation OTP optionnelle, vérification HTTP
docs/architecture/    Transcription V2 et sept flux
docs/decisions/       Choix techniques et limites
docs/testing/         Résultats des vérifications exécutées
docker-compose.yml    PostgreSQL, migration, API et application web
```

Le portail et le back-office forment une seule application React et partageront **un seul
Azure App Service** lors de la phase 7. Les configurations cloud restent planifiées.

## Exploitation locale et dépannage

```powershell
docker compose ps -a
docker compose logs --tail 50 api migrate db
docker compose logs --tail 50 web
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

- [Feuille de route complète et état des 10 phases](docs/ROADMAP.md)
- [Architecture V2 et hypothèses](docs/architecture/v2.md)
- [Décisions du socle local](docs/decisions/0001-socle-local.md)
- [Vérifications de la phase 1](docs/testing/phase-1.md)
- [Conception phase 2](docs/decisions/0002-domaine-electoral.md)
- [Modèle relationnel](docs/database/phase-2.md)
- [API phase 2 et exemples](docs/api/phase-2.md)
- [Vérifications de la phase 2](docs/testing/phase-2.md)
- [Choix d'authentification et RBAC](docs/decisions/0003-authentification.md)
- [Schéma de sécurité phase 3](docs/database/phase-3.md)
- [API et permissions phase 3](docs/api/phase-3.md)
- [Vérifications de la phase 3](docs/testing/phase-3.md)
- [Application web et parcours phase 4](docs/api/phase-4.md)
- [Vérifications de la phase 4](docs/testing/phase-4.md)
- [Phase 5 en cours : documents, incidents et adaptateur S3](docs/api/phase-5.md)
- [Vérifications intermédiaires de la phase 5](docs/testing/phase-5.md)
- [Préparation AWS-3 : Terraform, IAM et RDS](docs/infrastructure/aws-3-plan.md)
- [Préparation AWS-4A : backend TLS pour RDS](docs/infrastructure/aws-4a-backend-rds.md)
- [Préparation AWS-4B : RDS privé et runner contrôlé](docs/infrastructure/aws-4b-rds-plan.md)
- [Préparation AWS-5A : Lambda PV idempotente](docs/infrastructure/aws-5a-lambda-pv.md)
- [Architecture et contrats AWS à deux comptes](docs/infrastructure/aws-two-accounts.md)
- [Démarrage de Badreddine sur le compte AWS B](docs/infrastructure/aws-account-b-onboarding.md)

**IMPLÉMENTÉ :** application React responsive, cycle des PV, validation humaine, RBAC,
administration, consultation citoyenne, pièces justificatives privées PDF/JPEG/PNG et
incidents avec photographies privées JPEG/PNG.
Le backend reste l'autorité pour chaque permission.
**TESTÉ :** build de production, 20 tests frontend, 134 tests backend, migrations 0004/0005,
stack Docker, volume documentaire, dépôt, téléchargement et suppression d'un PDF fictif.
**QUALIFIÉ SUR AWS :** bucket S3 privé, chiffrement, versioning et parcours documentaire.
**DÉPLOYÉ DANS LE COMPTE A :** bucket adopté dans Terraform, VPC et RDS PostgreSQL 16
privés, API de secours EC2 qualifiée via SSM. Lambda PV, Lambda OTP et SNS suivent
dans le compte B. Le basculement GCP reste à qualifier.

Pour vérifier les sessions sans modifier `.env`, après seed et bootstrap, depuis la racine :

```powershell
.\.venv\Scripts\python.exe scripts/smoke_phase3.py
```

Ce script utilise les identifiants initiaux du fichier local, lance Uvicorn sur un port
éphémère, vérifie les trois rôles et le CRUD d'un scrutin fictif temporaire, supprime ce
scrutin, révoque ses sessions et arrête le serveur. Des événements d'audit sont conservés.
Sous WSL : `.venv/bin/python scripts/smoke_phase3.py`. Les limites de connexion s'appliquent
aussi au script ; attendre leur expiration après plusieurs exécutions rapprochées.

Prochain jalon : installer Terraform, valider le plan d'import S3 sans changement puis
implémenter TLS RDS côté backend. Aucun `terraform apply`, RDS, Lambda ou SMS réel ne doit
être lancé sans validation explicite du plan, de la connectivité et du budget.
