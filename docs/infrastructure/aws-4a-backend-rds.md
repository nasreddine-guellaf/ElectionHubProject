# AWS-4A — Préparation FastAPI pour RDS PostgreSQL

Date : 24 novembre 2026. Cette tranche prépare le backend sans créer RDS, sans appliquer
Terraform et sans migrer de données.

## Configuration ajoutée

| Variable | Défaut local | Cible RDS |
|---|---:|---:|
| `POSTGRES_SSLMODE` | `disable` | `verify-full` obligatoire |
| `POSTGRES_SSLROOTCERT` | absent | chemin absolu vers le bundle CA RDS |
| `POSTGRES_CONNECT_TIMEOUT_SECONDS` | `3` | ajustable de 1 à 30 secondes |
| `POSTGRES_POOL_SIZE` | `5` | connexions persistantes par processus |
| `POSTGRES_MAX_OVERFLOW` | `5` | connexions supplémentaires maximales |
| `POSTGRES_POOL_TIMEOUT_SECONDS` | `5` | attente maximale d'une connexion |
| `POSTGRES_POOL_RECYCLE_SECONDS` | `300` | renouvellement préventif des connexions |

Le mode local reste explicitement non TLS pour le conteneur PostgreSQL de développement.
Lorsque `APP_ENV=cloud` ou que l'hôte se termine par un domaine RDS AWS, le démarrage exige
`verify-full`. `verify-ca` et `verify-full` exigent un fichier existant et analysable par le
chargeur de certificats Python. Une CA absente, illisible ou invalide bloque le démarrage.

Exemple cible, sans valeur secrète :

```dotenv
APP_ENV=cloud
POSTGRES_HOST=electionhub.example.eu-north-1.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DB=electionhub
POSTGRES_USER=electionhub_app
POSTGRES_SSLMODE=verify-full
POSTGRES_SSLROOTCERT=/etc/ssl/certs/aws-rds-global-bundle.pem
POSTGRES_CONNECT_TIMEOUT_SECONDS=3
POSTGRES_POOL_SIZE=5
POSTGRES_MAX_OVERFLOW=5
POSTGRES_POOL_TIMEOUT_SECONDS=5
POSTGRES_POOL_RECYCLE_SECONDS=300
```

Le mot de passe n'appartient pas au fichier ni à l'image. Il sera injecté depuis GCP Secret
Manager après création d'un utilisateur PostgreSQL applicatif sans privilèges de propriétaire.

## Connexions SQLAlchemy/Psycopg

`create_db_engine` transmet `sslmode`, `sslrootcert` et le délai de connexion directement à
Psycopg. Le `QueuePool` SQLAlchemy conserve `pool_pre_ping` et borne le nombre maximal de
connexions simultanées à `pool_size + max_overflow`, soit 10 par processus avec les défauts.
`pool_recycle` remplace les connexions anciennes avant leur réutilisation.

Le nombre de workers devra être choisi avec la formule suivante avant GCP :

```text
connexions maximales API = workers × (POSTGRES_POOL_SIZE + POSTGRES_MAX_OVERFLOW)
```

Il faut conserver une marge pour Alembic, Lambda PV, les opérations administratives et les
connexions RDS internes.

## Compatibilité et vérifications

- PostgreSQL local : image `postgres:16-bookworm`, serveur 16.16 détecté ;
- cible planifiée : RDS PostgreSQL 16.15, même version majeure ;
- Alembic utilise le même constructeur d'engine en mode connecté ;
- `alembic upgrade head` et `alembic check` réussissent localement ;
- tests dédiés : mode local, obligation RDS/cloud, CA manquante, CA invalide, CA valide,
  transmission Psycopg, bornes du pool et préservation du workflow non TLS ;
- aucune option, extension ou requête spécifique au PostgreSQL local n'a été introduite.

Résultats de recette : **117 tests backend réussis**, Ruff et formatage réussis,
`docker compose config` valide, migration reconstruite et exécutée, `alembic check`
réussi sur l'hôte et dans le conteneur. L'unique avertissement restant vient de la
dépréciation du client de test Starlette et ne concerne pas RDS.

## Déploiement futur

1. Télécharger le bundle officiel `global-bundle.pem` depuis AWS pendant la construction ou
   le déploiement, vérifier son origine et le monter en lecture seule dans le conteneur.
2. Injecter les variables non secrètes et le secret applicatif depuis la plateforme cible.
3. Tester `verify-full` avec le véritable nom DNS RDS, jamais avec une adresse IP ou un alias.
4. Vérifier `rds.force_ssl=1`, `pg_stat_ssl.ssl=true`, la chaîne de certificat et un échec
   attendu avec `sslmode=disable`.
5. Exécuter Alembic sur une base RDS vide, puis un test de sauvegarde/restauration avec
   données synthétiques avant toute migration.

## Blocages restants

- aucune instance RDS ni connectivité GCP→RDS n'existe ;
- le bundle CA RDS n'est pas encore monté dans une image ou un service cloud ;
- le rôle IAM applicatif, le VPC et le groupe de sécurité restent seulement planifiés ;
- l'utilisateur SQL applicatif et son secret GCP ne peuvent être créés avant RDS ;
- les limites du pool devront être recalculées après choix du nombre de workers GCP/Lambda.
