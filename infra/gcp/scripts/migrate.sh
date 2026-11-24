#!/usr/bin/env bash
# Migration Alembic explicite et unique (jamais lancée par les instances du MIG).
#
# À exécuter UNE FOIS par version, depuis une machine autorisée à joindre RDS (en pratique :
# une IP présente dans le groupe de sécurité RDS) et authentifiée sur GCP (gcloud auth login).
# Elle lit le mot de passe dans Secret Manager, ne l'écrit jamais sur disque ni dans l'historique,
# et utilise l'image exacte qui sera déployée.
#
#   PROJECT_ID=... REGION=europe-north1 IMAGE_TAG=0.1.0 \
#   RDS_HOST=...rds.amazonaws.com RDS_CA_FILE=./global-bundle.pem \
#   ./infra/gcp/scripts/migrate.sh [--dry-run]
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID requis}"
: "${REGION:?REGION requis}"
: "${IMAGE_TAG:?IMAGE_TAG requis}"
: "${RDS_HOST:?RDS_HOST requis}"
: "${RDS_CA_FILE:?RDS_CA_FILE requis (bundle CA AWS RDS)}"
NAME_PREFIX="${NAME_PREFIX:-electionhub}"
POSTGRES_DB="${POSTGRES_DB:-electionhub}"
POSTGRES_USER="${POSTGRES_USER:-electionhub_app}"
RDS_PORT="${RDS_PORT:-5432}"

if [ "$IMAGE_TAG" = "latest" ]; then
  echo "Refus : utiliser un tag explicite, pas 'latest'." >&2
  exit 2
fi
[ -f "$RDS_CA_FILE" ] || { echo "Bundle CA introuvable : $RDS_CA_FILE" >&2; exit 2; }

IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$NAME_PREFIX-images/api:$IMAGE_TAG"
SECRET="$NAME_PREFIX-postgres-password"

if [ "${1:-}" = "--dry-run" ]; then
  echo "Image      : $IMAGE"
  echo "Secret     : $SECRET (projet $PROJECT_ID)"
  echo "Base       : $POSTGRES_USER@$RDS_HOST:$RDS_PORT/$POSTGRES_DB (verify-full)"
  echo "Commande   : alembic upgrade head"
  exit 0
fi

ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT
chmod 0600 "$ENV_FILE"
{
  echo "APP_ENV=cloud"
  echo "POSTGRES_HOST=$RDS_HOST"
  echo "POSTGRES_PORT=$RDS_PORT"
  echo "POSTGRES_DB=$POSTGRES_DB"
  echo "POSTGRES_USER=$POSTGRES_USER"
  echo "POSTGRES_SSLMODE=verify-full"
  echo "POSTGRES_SSLROOTCERT=/etc/electionhub/rds-ca.pem"
  printf 'POSTGRES_PASSWORD=%s\n' "$(gcloud secrets versions access latest --secret="$SECRET" --project="$PROJECT_ID" | tr -d '\r\n')"
} > "$ENV_FILE"

gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
docker run --rm --env-file "$ENV_FILE" \
  -v "$(cd "$(dirname "$RDS_CA_FILE")" && pwd)/$(basename "$RDS_CA_FILE"):/etc/electionhub/rds-ca.pem:ro" \
  "$IMAGE" alembic upgrade head
echo "Migration terminée. Les instances peuvent maintenant passer la sonde /health."
