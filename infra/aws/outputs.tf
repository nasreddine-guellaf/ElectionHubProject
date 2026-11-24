output "documents_bucket_name" {
  description = "Imported ElectionHub document bucket."
  value       = aws_s3_bucket.documents.id
}

output "application_role_arn" {
  description = "Least-privilege application role, when enabled."
  value       = var.enable_new_resources ? aws_iam_role.application[0].arn : null
}

output "rds_endpoint" {
  description = "RDS hostname; never use its resolved IP for TLS verification."
  value       = var.enable_new_resources ? aws_db_instance.electionhub[0].address : null
}

output "rds_master_secret_arn" {
  description = "RDS-managed bootstrap secret ARN; the application must not use the master user."
  value = var.enable_new_resources ? (
    length(aws_db_instance.electionhub[0].master_user_secret) > 0
    ? aws_db_instance.electionhub[0].master_user_secret[0].secret_arn
    : null
  ) : null
  sensitive = true
}
