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
  description = "Allows plans for IAM, VPC, and RDS resources. Keep false for the S3 adoption plan."
  type        = bool
  default     = false
}

variable "rds_publicly_accessible" {
  description = "Expose an RDS public endpoint. Use only with exact /32 ingress CIDRs and TLS."
  type        = bool
  default     = false

  validation {
    condition     = !var.rds_publicly_accessible || length(var.postgres_ingress_cidrs) > 0
    error_message = "A public RDS endpoint requires at least one explicit ingress CIDR."
  }
}

variable "postgres_ingress_cidrs" {
  description = "Approved fixed client CIDRs. Never use 0.0.0.0/0."
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for cidr in var.postgres_ingress_cidrs :
      can(cidrhost(cidr, 0)) && cidr != "0.0.0.0/0" && cidr != "::/0"
    ])
    error_message = "Use valid, restricted CIDRs; world-open database access is forbidden."
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
