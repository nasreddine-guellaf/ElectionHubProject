\set ON_ERROR_STOP on

-- Run while authenticated as electionhub_migrator after Alembic.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
  TO :"application_username";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public
  TO :"application_username";

-- Lambda PV authenticates through RDS IAM and can touch only its event tables.
GRANT SELECT (id, object_key, size_bytes, sha256)
  ON TABLE report_documents TO :"event_username";
GRANT UPDATE (processing_status, processed_at, failure_reason)
  ON TABLE report_documents TO :"event_username";
GRANT SELECT (provider_event_id), INSERT (id, provider_event_id, document_id, event_name)
  ON TABLE object_events TO :"event_username";
