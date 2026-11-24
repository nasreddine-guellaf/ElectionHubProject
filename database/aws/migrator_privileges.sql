\set ON_ERROR_STOP on

-- Run while authenticated as electionhub_migrator before Alembic.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"application_username";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"application_username";
