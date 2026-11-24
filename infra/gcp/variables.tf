variable "project_id" {
  description = "GCP project ID. Required so a plan can never target another project."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project ID (6-30 chars, lowercase, digits, hyphens)."
  }
}

variable "enable_new_resources" {
  description = "Safety switch. While false, the plan creates nothing. Set true only after explicit approval."
  type        = bool
  default     = false
}

variable "region" {
  description = "GCP region. To be confirmed; europe-north1 is closest to the AWS eu-north-1 database."
  type        = string
  default     = "europe-north1"
}

variable "name_prefix" {
  description = "Prefix for resource names (lowercase letters, digits, hyphens)."
  type        = string
  default     = "electionhub"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.name_prefix))
    error_message = "name_prefix must be 3-20 characters, start with a letter: lowercase letters, digits, hyphens."
  }
}

variable "subnet_cidr" {
  description = "Private subnet used by API instances (no external IPs)."
  type        = string
  default     = "10.20.0.0/24"
}

variable "machine_type" {
  description = "Instance machine type. e2-small is enough for a demonstration."
  type        = string
  default     = "e2-small"
}

variable "api_image_tag" {
  description = "Immutable tag of the API image in Artifact Registry. 'latest' is rejected."
  type        = string
  nullable    = false

  validation {
    condition     = var.api_image_tag != "latest"
    error_message = "Use an explicit version tag, not 'latest'."
  }
}

variable "min_replicas" {
  description = "Minimum number of API instances."
  type        = number
  default     = 1
}

variable "max_replicas" {
  description = "Maximum number of API instances. Check the RDS connection budget before raising it."
  type        = number
  default     = 2
}

variable "api_workers" {
  description = "Uvicorn workers per instance (UVICORN_WORKERS)."
  type        = number
  default     = 1

  validation {
    condition     = var.api_workers >= 1 && var.api_workers <= 4
    error_message = "api_workers must be between 1 and 4."
  }
}

variable "postgres_pool_size" {
  description = "SQLAlchemy persistent connections per worker."
  type        = number
  default     = 5
}

variable "postgres_max_overflow" {
  description = "SQLAlchemy extra connections per worker."
  type        = number
  default     = 5
}

variable "domain" {
  description = "Public DNS name of the API (Google-managed certificate). Its A record must point to the load balancer IP."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^([a-z0-9-]+\\.)+[a-z]{2,}$", var.domain))
    error_message = "domain must be a lowercase DNS name such as api.example.org."
  }
}

variable "rds_host" {
  description = "RDS endpoint hostname (…rds.amazonaws.com). Known only after AWS creates the database."
  type        = string
  nullable    = false
}

variable "rds_port" {
  description = "RDS PostgreSQL port."
  type        = number
  default     = 5432
}

variable "postgres_db" {
  description = "Database name."
  type        = string
  default     = "electionhub"
}

variable "postgres_user" {
  description = "Non-owner application SQL user."
  type        = string
  default     = "electionhub_app"
}

variable "aws_region" {
  description = "AWS region of the S3 bucket."
  type        = string
  default     = "eu-north-1"
}

variable "s3_bucket" {
  description = "Private S3 bucket for supporting documents."
  type        = string
  nullable    = false
}

variable "aws_role_arn" {
  description = "AWS IAM role the API assumes with a Google-issued OIDC token (no long-lived AWS keys)."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", var.aws_role_arn))
    error_message = "aws_role_arn must be an IAM role ARN."
  }
}

variable "aws_token_audience" {
  description = "Audience claim of the Google ID token; must match the AWS role trust policy."
  type        = string
  default     = "sts.amazonaws.com"
}

variable "allow_iap_ssh" {
  description = "Open SSH only from Google IAP (35.235.240.0/20) for troubleshooting. Off by default."
  type        = bool
  default     = false
}
