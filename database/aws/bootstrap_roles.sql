\set ON_ERROR_STOP on

-- Required psql variables: database_name, application_username,
-- application_password, migrator_username, migrator_password, event_username.
-- RDS administrators can manage these roles without changing protected attributes.
SELECT 1 / CASE WHEN EXISTS (
  SELECT 1 FROM pg_roles
  WHERE rolname IN (:'application_username', :'migrator_username', :'event_username')
    AND (rolsuper OR rolreplication)
) THEN 0 ELSE 1 END AS require_unprivileged_roles;

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
  :'application_username',
  :'application_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'application_username')
\gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L NOCREATEDB NOCREATEROLE',
  :'application_username',
  :'application_password'
)
\gexec

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
  :'migrator_username',
  :'migrator_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator_username')
\gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L NOCREATEDB NOCREATEROLE',
  :'migrator_username',
  :'migrator_password'
)
\gexec

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
  :'event_username'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'event_username')
\gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN NOCREATEDB NOCREATEROLE',
  :'event_username'
)
\gexec

SELECT format('GRANT rds_iam TO %I', :'event_username')
\gexec

SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'database_name')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'application_username')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'migrator_username')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'event_username')
\gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'application_username')
\gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'migrator_username')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'event_username')
\gexec
