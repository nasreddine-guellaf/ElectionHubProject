export type Role = 'ADMIN' | 'AGENT' | 'VALIDATOR' | 'CITIZEN';
export type Status = 'DRAFT' | 'SUBMITTED' | 'PROCESSING' | 'PENDING_VALIDATION' | 'APPROVED' | 'REJECTED' | 'PUBLISHED' | 'PROCESSING_FAILED';
export interface Profile { id: string; display_name: string; role: Role }
export interface Token { access_token: string; expires_at: string; token_type: string }
export interface Account extends Profile { username: string; active: boolean }
export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export interface Station { id: string; code: string; name: string; registered_voters: number }
export interface Election { id: string; code: string; name: string; start_date: string; end_date: string; enforce_ballot_equation: boolean }
export interface Candidate { id: string; code: string; name: string }
export interface ElectionStation { election_id: string; polling_station_id: string; registered_voters: number }
export interface Assignment { election_id: string; polling_station_id: string; user_id: string }
export interface Report { id: string; election_id: string; polling_station_id: string; created_by: string; current_revision: number; created_at: string }
export interface Result { candidate_id: string; votes: number }
export interface Revision { id: string; report_id: string; election_id: string; revision_number: number; status: Status; edit_version: number; created_by: string; revision_reason: string; registered_voters: number; enforce_ballot_equation: boolean; ballots_cast: number; valid_votes: number; blank_votes: number; invalid_votes: number; results: Result[]; created_at: string; submitted_at: string | null }
export interface ReportRow extends Report { revision: Revision }
export interface ReportEvent { id: string; revision_id: string; actor_id: string; action: string; edit_version: number; note: string; created_at: string }
export interface Validation { id: string; revision_id: string; validator_id: string; decision: string; reason: string; created_at: string }
export interface ReportDocument { id: string; revision_id: string; uploaded_by: string; original_filename: string; media_type: string; size_bytes: number; sha256: string; storage_provider: 'LOCAL' | 'S3'; processing_status: 'STORED' | 'PROCESSED' | 'FAILED'; created_at: string; processed_at: string | null; failure_reason: string | null }
export interface Audit { id: string; actor_id: string | null; target_id: string | null; action: string; resource: string | null; created_at: string }
