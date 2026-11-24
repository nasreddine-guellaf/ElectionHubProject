data "aws_iam_policy_document" "application_trust" {
  statement {
    sid     = "AllowLocalDevelopmentAssumption"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.aws_account_id}:role/managed/AccountFullAccessRole"]
    }
  }
}

resource "aws_iam_role" "application" {
  count = var.enable_new_resources ? 1 : 0

  name                 = "ElectionHubApplicationRole"
  path                 = "/electionhub/"
  description          = "Runtime access for the ElectionHub API; never a human administrator role."
  assume_role_policy   = data.aws_iam_policy_document.application_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "application_s3" {
  statement {
    sid    = "ReadBucketMetadata"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucketMultipartUploads",
    ]
    resources = [aws_s3_bucket.documents.arn]
  }

  statement {
    sid    = "ReadAndDeleteReportObjects"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.documents.arn}/reports/*"]
  }

  statement {
    sid       = "UploadEncryptedReportObjects"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.documents.arn}/reports/*"]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["AES256"]
    }
  }
}

resource "aws_iam_role_policy" "application_s3" {
  count = var.enable_new_resources ? 1 : 0

  name   = "ElectionHubPrivateDocuments"
  role   = aws_iam_role.application[0].id
  policy = data.aws_iam_policy_document.application_s3.json
}
