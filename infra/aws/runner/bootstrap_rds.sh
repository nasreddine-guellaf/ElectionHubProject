#!/bin/bash
set -euo pipefail
umask 077

: "${RDS_ENDPOINT:?RDS_ENDPOINT is required}"
: "${RDS_MASTER_SECRET_ARN:?RDS_MASTER_SECRET_ARN is required}"
: "${APPLICATION_SECRET_ARN:?APPLICATION_SECRET_ARN is required}"
: "${ELECTIONHUB_COMMIT:?ELECTIONHUB_COMMIT is required}"

AWS_REGION="${AWS_REGION:-eu-north-1}"
DATABASE_NAME="${DATABASE_NAME:-electionhub}"
APPLICATION_USERNAME="${APPLICATION_USERNAME:-electionhub_app}"
MIGRATOR_USERNAME="${MIGRATOR_USERNAME:-electionhub_migrator}"
EVENT_USERNAME="${EVENT_USERNAME:-electionhub_event_processor}"
REPOSITORY_URL="${REPOSITORY_URL:-https://github.com/nasreddine-guellaf/ElectionHubProject.git}"
CA_FILE="/opt/electionhub/eu-north-1-bundle.pem"
WORK_DIR="/run/electionhub-bootstrap"
SOURCE_DIR="/opt/electionhub/source"
VENV_DIR="/opt/electionhub/venv"

[[ "$RDS_ENDPOINT" =~ ^[a-zA-Z0-9.-]+\.rds\.amazonaws\.com$ ]]
[[ "$DATABASE_NAME" =~ ^[a-z][a-z0-9_]{2,30}$ ]]
[[ "$APPLICATION_USERNAME" =~ ^[a-z][a-z0-9_]{2,30}$ ]]
[[ "$MIGRATOR_USERNAME" =~ ^[a-z][a-z0-9_]{2,30}$ ]]
[[ "$EVENT_USERNAME" =~ ^[a-z][a-z0-9_]{2,30}$ ]]
[[ "$ELECTIONHUB_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -s "$CA_FILE"

install -d -m 0700 "$WORK_DIR"
cleanup() {
  rm -f "$WORK_DIR/master.json" "$WORK_DIR/variables.sql" "$WORK_DIR/application-secret.json"
  unset MASTER_PASSWORD APPLICATION_PASSWORD MIGRATOR_PASSWORD
}
trap cleanup EXIT

aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$RDS_MASTER_SECRET_ARN" \
  --query SecretString \
  --output text > "$WORK_DIR/master.json"

MASTER_USERNAME="$(jq -er .username "$WORK_DIR/master.json")"
MASTER_PASSWORD="$(jq -er .password "$WORK_DIR/master.json")"
APPLICATION_PASSWORD="$(openssl rand -hex 32)"
MIGRATOR_PASSWORD="$(openssl rand -hex 32)"

rm -rf "$SOURCE_DIR" "$VENV_DIR"
git init --quiet "$SOURCE_DIR"
git -C "$SOURCE_DIR" remote add origin "$REPOSITORY_URL"
git -C "$SOURCE_DIR" fetch --quiet --depth 1 origin "$ELECTIONHUB_COMMIT"
git -C "$SOURCE_DIR" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$SOURCE_DIR" rev-parse HEAD)" = "$ELECTIONHUB_COMMIT"

cat > "$WORK_DIR/variables.sql" <<EOF
\set database_name '$DATABASE_NAME'
\set application_username '$APPLICATION_USERNAME'
\set application_password '$APPLICATION_PASSWORD'
\set migrator_username '$MIGRATOR_USERNAME'
\set migrator_password '$MIGRATOR_PASSWORD'
\set event_username '$EVENT_USERNAME'
\i $SOURCE_DIR/database/aws/bootstrap_roles.sql
EOF

PGPASSWORD="$MASTER_PASSWORD" PGSSLMODE=verify-full PGSSLROOTCERT="$CA_FILE" \
  psql --host "$RDS_ENDPOINT" --port 5432 --username "$MASTER_USERNAME" \
  --dbname "$DATABASE_NAME" --file "$WORK_DIR/variables.sql"

PGPASSWORD="$MIGRATOR_PASSWORD" PGSSLMODE=verify-full PGSSLROOTCERT="$CA_FILE" \
  psql --host "$RDS_ENDPOINT" --port 5432 --username "$MIGRATOR_USERNAME" \
  --dbname "$DATABASE_NAME" --set "application_username=$APPLICATION_USERNAME" \
  --file "$SOURCE_DIR/database/aws/migrator_privileges.sql"

python3.11 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --disable-pip-version-check --no-cache-dir \
  --requirement "$SOURCE_DIR/backend/requirements.lock"

export APP_ENV=cloud
export POSTGRES_HOST="$RDS_ENDPOINT"
export POSTGRES_PORT=5432
export POSTGRES_DB="$DATABASE_NAME"
export POSTGRES_USER="$MIGRATOR_USERNAME"
export POSTGRES_PASSWORD="$MIGRATOR_PASSWORD"
export POSTGRES_SSLMODE=verify-full
export POSTGRES_SSLROOTCERT="$CA_FILE"

(
  cd "$SOURCE_DIR/backend"
  "$VENV_DIR/bin/alembic" upgrade head
  "$VENV_DIR/bin/alembic" check
)

PGPASSWORD="$MIGRATOR_PASSWORD" PGSSLMODE=verify-full PGSSLROOTCERT="$CA_FILE" \
  psql --host "$RDS_ENDPOINT" --port 5432 --username "$MIGRATOR_USERNAME" \
  --dbname "$DATABASE_NAME" --set "application_username=$APPLICATION_USERNAME" \
  --set "event_username=$EVENT_USERNAME" \
  --file "$SOURCE_DIR/database/aws/grant_runtime.sql"

PGPASSWORD="$APPLICATION_PASSWORD" PGSSLMODE=verify-full PGSSLROOTCERT="$CA_FILE" \
  psql --host "$RDS_ENDPOINT" --port 5432 --username "$APPLICATION_USERNAME" \
  --dbname "$DATABASE_NAME" --tuples-only --no-align \
  --command "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid();"

if PGPASSWORD="$APPLICATION_PASSWORD" PGSSLMODE=verify-full PGSSLROOTCERT="$CA_FILE" \
  psql --host "$RDS_ENDPOINT" --port 5432 --username "$APPLICATION_USERNAME" \
  --dbname "$DATABASE_NAME" --command "CREATE TABLE public.electionhub_forbidden_probe(id integer);"
then
  PGPASSWORD="$MASTER_PASSWORD" PGSSLMODE=verify-full PGSSLROOTCERT="$CA_FILE" \
    psql --host "$RDS_ENDPOINT" --port 5432 --username "$MASTER_USERNAME" \
    --dbname "$DATABASE_NAME" --command "DROP TABLE IF EXISTS public.electionhub_forbidden_probe;"
  echo "The runtime role unexpectedly has CREATE privilege." >&2
  exit 1
fi

if PGPASSWORD="$MASTER_PASSWORD" PGSSLMODE=disable \
  psql --host "$RDS_ENDPOINT" --port 5432 --username "$MASTER_USERNAME" \
  --dbname "$DATABASE_NAME" --command "SELECT 1;"
then
  echo "RDS unexpectedly accepted a non-TLS connection." >&2
  exit 1
fi

jq -n \
  --arg username "$APPLICATION_USERNAME" \
  --arg password "$APPLICATION_PASSWORD" \
  --arg host "$RDS_ENDPOINT" \
  --arg database "$DATABASE_NAME" \
  '{username:$username,password:$password,host:$host,port:5432,database:$database}' \
  > "$WORK_DIR/application-secret.json"

aws secretsmanager put-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$APPLICATION_SECRET_ARN" \
  --secret-string "file://$WORK_DIR/application-secret.json" > /dev/null

PGPASSWORD="$MASTER_PASSWORD" PGSSLMODE=verify-full PGSSLROOTCERT="$CA_FILE" \
  psql --host "$RDS_ENDPOINT" --port 5432 --username "$MASTER_USERNAME" \
  --dbname "$DATABASE_NAME" \
  --command "ALTER ROLE \"$MIGRATOR_USERNAME\" NOLOGIN;"

echo "RDS TLS, Alembic, and the non-owner runtime role were qualified successfully."
