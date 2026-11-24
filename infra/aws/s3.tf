resource "aws_s3_bucket" "documents" {
  bucket        = var.existing_s3_bucket_name
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = "Enabled"
  }

  lifecycle {
    prevent_destroy = true
  }
}

data "aws_iam_policy_document" "bucket_tls" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.documents.arn,
      "${aws_s3_bucket.documents.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "documents" {
  bucket = aws_s3_bucket.documents.id
  policy = data.aws_iam_policy_document.bucket_tls.json

  lifecycle {
    prevent_destroy = true
  }
}

import {
  to = aws_s3_bucket.documents
  id = var.existing_s3_bucket_name
}

import {
  to = aws_s3_bucket_public_access_block.documents
  id = var.existing_s3_bucket_name
}

import {
  to = aws_s3_bucket_ownership_controls.documents
  id = var.existing_s3_bucket_name
}

import {
  to = aws_s3_bucket_server_side_encryption_configuration.documents
  id = var.existing_s3_bucket_name
}

import {
  to = aws_s3_bucket_versioning.documents
  id = var.existing_s3_bucket_name
}

import {
  to = aws_s3_bucket_policy.documents
  id = var.existing_s3_bucket_name
}
