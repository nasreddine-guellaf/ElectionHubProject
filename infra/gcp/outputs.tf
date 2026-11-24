output "lb_ip_address" {
  description = "Create the DNS A record for var.domain with this address (null while disabled)."
  value       = one(google_compute_global_address.lb[*].address)
}

output "api_url" {
  description = "Stable HTTPS URL to give to the Azure frontend as API_UPSTREAM."
  value       = "https://${var.domain}"
}

output "nat_egress_ipv4" {
  description = "Fixed egress IPv4 of the API instances, for any AWS-side allow-list (RDS stays private: see docs/infrastructure/phase-6-gcp.md)."
  value       = one(google_compute_address.nat_egress[*].address)
}

output "service_account_email" {
  description = "Instance identity."
  value       = one(google_service_account.api[*].email)
}

output "service_account_unique_id" {
  description = "Numeric ID (the 'sub' claim of the Google ID token) for the AWS role trust policy."
  value       = one(google_service_account.api[*].unique_id)
}

output "image_repository" {
  description = "Artifact Registry path to push the API image to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${local.repo_id}"
}

output "secret_ids" {
  description = "Secret Manager containers to fill out of band (no value is stored by Terraform)."
  value = {
    postgres_password = one(google_secret_manager_secret.postgres_password[*].secret_id)
    rds_ca_bundle     = one(google_secret_manager_secret.rds_ca_bundle[*].secret_id)
  }
}

output "max_db_connections" {
  description = "Worst-case RDS connections: max_replicas x workers x (pool_size + max_overflow). Keep below the RDS limit minus a safety margin."
  value       = local.max_connection
}
