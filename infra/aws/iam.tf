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
    sid    = "ReadAndDeleteApplicationObjects"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "${aws_s3_bucket.documents.arn}/reports/*",
      "${aws_s3_bucket.documents.arn}/incidents/*",
    ]
  }

  statement {
    sid     = "UploadEncryptedApplicationObjects"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.documents.arn}/reports/*",
      "${aws_s3_bucket.documents.arn}/incidents/*",
    ]

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

data "aws_iam_policy_document" "test_runner_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "test_runner" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  name               = "ElectionHubTestRunnerRole"
  path               = "/electionhub/"
  description        = "Temporary SSM runner for RDS TLS, role bootstrap, and Alembic qualification."
  assume_role_policy = data.aws_iam_policy_document.test_runner_trust.json

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
    Temporary   = "true"
  }
}

resource "aws_iam_role_policy_attachment" "test_runner_ssm" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  role       = aws_iam_role.test_runner[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "test_runner_database" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  statement {
    sid     = "ReadRDSManagedBootstrapSecret"
    effect  = "Allow"
    actions = ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"]
    resources = [
      aws_db_instance.electionhub[0].master_user_secret[0].secret_arn,
    ]
  }

  statement {
    sid    = "WriteApplicationDatabaseSecret"
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
      "secretsmanager:PutSecretValue",
    ]
    resources = [
      aws_secretsmanager_secret.application_database[0].arn,
    ]
  }
}

resource "aws_iam_role_policy" "test_runner_database" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  name   = "ElectionHubDatabaseBootstrap"
  role   = aws_iam_role.test_runner[0].id
  policy = data.aws_iam_policy_document.test_runner_database[0].json
}

resource "aws_iam_instance_profile" "test_runner" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  name = "ElectionHubTestRunner"
  path = "/electionhub/"
  role = aws_iam_role.test_runner[0].name
}
