variable "aws_region" {
  description = "AWS project region. The current project is fixed to Stockholm."
  type        = string
  default     = "eu-north-1"

  validation {
    condition     = var.aws_region == "eu-north-1"
    error_message = "This AWS project is restricted to eu-north-1."
  }
}

variable "aws_profile" {
  description = "Temporary aws login profile used only by Terraform."
  type        = string
  default     = "electionhub-demo"
}

variable "aws_account_id" {
  description = "Expected AWS account ID. Supplying it prevents accidental cross-account plans."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "existing_s3_bucket_name" {
  description = "Existing private ElectionHub bucket to import; Terraform must not recreate it."
  type        = string
  nullable    = false
}

variable "enable_new_resources" {
  description = "Allows plans for IAM, VPC, Secrets Manager, and RDS. Keep false for S3-only checks."
  type        = bool
  default     = false
}

variable "enable_test_runner" {
  description = "Creates one temporary SSM-managed EC2 runner. Requires enable_new_resources=true."
  type        = bool
  default     = false
}

variable "rds_engine_version" {
  description = "Qualified PostgreSQL 16 minor version available in eu-north-1."
  type        = string
  default     = "16.15"

  validation {
    condition     = startswith(var.rds_engine_version, "16.")
    error_message = "ElectionHub AWS-4B is restricted to PostgreSQL major version 16."
  }
}

variable "rds_instance_class" {
  description = "Free Plan eligible RDS class selected for the demonstration."
  type        = string
  default     = "db.t4g.micro"

  validation {
    condition     = var.rds_instance_class == "db.t4g.micro"
    error_message = "AWS-4B only approves db.t4g.micro; review cost and memory before changing it."
  }
}

variable "rds_backup_retention_days" {
  description = "Automated backup retention for the controlled deployment."
  type        = number
  default     = 7

  validation {
    condition     = var.rds_backup_retention_days >= 1 && var.rds_backup_retention_days <= 7
    error_message = "The demonstration retention window must remain between 1 and 7 days."
  }
}

variable "db_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "electionhub"
}

variable "db_master_username" {
  description = "Administrative bootstrap user; the application must use a separate DB role."
  type        = string
  default     = "electionhub_admin"
}

variable "db_application_username" {
  description = "Dedicated non-owner runtime login created after RDS provisioning."
  type        = string
  default     = "electionhub_app"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,30}$", var.db_application_username))
    error_message = "db_application_username must be a simple lowercase PostgreSQL identifier."
  }
}

variable "test_runner_instance_type" {
  description = "Short-lived ARM64 EC2 size used only for migration and TLS qualification."
  type        = string
  default     = "t4g.micro"

  validation {
    condition     = var.test_runner_instance_type == "t4g.micro"
    error_message = "AWS-4B only approves the Free Plan eligible t4g.micro test runner."
  }
}

variable "test_runner_ttl_hours" {
  description = "Automatic termination deadline for the optional test runner."
  type        = number
  default     = 2

  validation {
    condition     = var.test_runner_ttl_hours >= 1 && var.test_runner_ttl_hours <= 4
    error_message = "The temporary runner TTL must remain between 1 and 4 hours."
  }
}
