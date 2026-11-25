terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "local" {
    path = "../../.local/aws-account-b/pv-artifacts.tfstate"
  }
}

variable "enable_artifact_bucket" {
  type    = bool
  default = false
}

provider "aws" {
  region              = "eu-north-1"
  profile             = "electionhub-new-dev"
  allowed_account_ids = ["865579549007"]

  default_tags {
    tags = {
      Project     = "ElectionHub"
      Environment = "account-b-pv-artifacts"
    }
  }
}

resource "aws_s3_bucket" "pv" {
  count         = var.enable_artifact_bucket ? 1 : 0
  bucket        = "electionhub-pv-artifacts-865579549007-eu-north-1"
  force_destroy = false
}

resource "aws_s3_bucket_ownership_controls" "pv" {
  count  = length(aws_s3_bucket.pv)
  bucket = aws_s3_bucket.pv[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "pv" {
  count                   = length(aws_s3_bucket.pv)
  bucket                  = aws_s3_bucket.pv[0].id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "pv" {
  count  = length(aws_s3_bucket.pv)
  bucket = aws_s3_bucket.pv[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pv" {
  count  = length(aws_s3_bucket.pv)
  bucket = aws_s3_bucket.pv[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "pv" {
  count  = length(aws_s3_bucket.pv)
  bucket = aws_s3_bucket.pv[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.pv[0].arn, "${aws_s3_bucket.pv[0].arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.pv]
}

output "artifact_bucket_name" {
  value = one(aws_s3_bucket.pv[*].bucket)
}
