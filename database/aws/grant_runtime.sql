\set ON_ERROR_STOP on

-- Run while authenticated as electionhub_migrator after Alembic.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
  TO :"application_username";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public
  TO :"application_username";
