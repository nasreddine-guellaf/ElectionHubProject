locals {
  pv_lambda_package = abspath("${path.module}/${var.pv_lambda_package_path}")
}

data "aws_prefix_list" "s3" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0
  name  = "com.amazonaws.${var.aws_region}.s3"
}

data "aws_iam_policy_document" "pv_lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "pv_lambda" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  name               = "ElectionHubPvProcessorRole"
  path               = "/electionhub/"
  description        = "Least-privilege identity for idempotent S3 PV processing."
  assume_role_policy = data.aws_iam_policy_document.pv_lambda_assume.json

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

data "aws_iam_policy_document" "pv_lambda" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  statement {
    sid       = "ReadReportObjects"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.documents.arn}/reports/*"]
  }

  statement {
    sid     = "ConnectAsEventProcessor"
    actions = ["rds-db:connect"]
    resources = [
      "arn:aws:rds-db:${var.aws_region}:${var.aws_account_id}:dbuser:${aws_db_instance.electionhub[0].resource_id}/${var.db_event_username}",
    ]
  }

  statement {
    sid       = "WriteDeadLetterQueue"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.pv_lambda_dlq[0].arn]
  }

  statement {
    sid     = "WriteFunctionLogs"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "${aws_cloudwatch_log_group.pv_lambda[0].arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "pv_lambda" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  name   = "ElectionHubPvProcessor"
  role   = aws_iam_role.pv_lambda[0].id
  policy = data.aws_iam_policy_document.pv_lambda[0].json
}

resource "aws_security_group" "pv_lambda" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  name        = "electionhub-pv-lambda"
  description = "No ingress; PostgreSQL and regional S3 egress only"
  vpc_id      = aws_vpc.electionhub[0].id
  ingress     = []
  egress      = []

  tags = {
    Name        = "electionhub-pv-lambda"
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_vpc_security_group_egress_rule" "pv_lambda_postgres" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  security_group_id            = aws_security_group.pv_lambda[0].id
  description                  = "PostgreSQL only to ElectionHub RDS"
  referenced_security_group_id = aws_security_group.postgres[0].id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "pv_lambda_s3" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  security_group_id = aws_security_group.pv_lambda[0].id
  description       = "HTTPS only to the regional S3 prefix list"
  prefix_list_id    = data.aws_prefix_list.s3[0].id
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_pv_lambda" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  security_group_id            = aws_security_group.postgres[0].id
  description                  = "PostgreSQL only from Lambda PV"
  referenced_security_group_id = aws_security_group.pv_lambda[0].id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

data "aws_iam_policy_document" "pv_s3_endpoint" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  statement {
    sid       = "ReadOnlyReportObjects"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.documents.arn}/reports/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalArn"
      values   = [aws_iam_role.pv_lambda[0].arn]
    }
  }
}

resource "aws_vpc_endpoint" "s3" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  vpc_id            = aws_vpc.electionhub[0].id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.database[0].id]
  policy            = data.aws_iam_policy_document.pv_s3_endpoint[0].json

  tags = {
    Name        = "electionhub-s3"
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_sqs_queue" "pv_lambda_dlq" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  name                      = "electionhub-pv-processor-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_cloudwatch_log_group" "pv_lambda" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  name              = "/aws/lambda/electionhub-pv-processor"
  retention_in_days = 14

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_lambda_function" "pv_processor" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  function_name    = "electionhub-pv-processor"
  description      = "Validates private PV objects and records S3 events idempotently."
  role             = aws_iam_role.pv_lambda[0].arn
  runtime          = "python3.11"
  architectures    = ["x86_64"]
  handler          = "app.lambda_pv.lambda_handler"
  filename         = local.pv_lambda_package
  source_code_hash = filebase64sha256(local.pv_lambda_package)

  memory_size                    = 256
  timeout                        = 60
  reserved_concurrent_executions = 2

  dead_letter_config {
    target_arn = aws_sqs_queue.pv_lambda_dlq[0].arn
  }

  vpc_config {
    subnet_ids         = aws_subnet.database[*].id
    security_group_ids = [aws_security_group.pv_lambda[0].id]
  }

  environment {
    variables = {
      S3_BUCKET            = aws_s3_bucket.documents.id
      POSTGRES_HOST        = aws_db_instance.electionhub[0].address
      POSTGRES_PORT        = tostring(aws_db_instance.electionhub[0].port)
      POSTGRES_DB          = var.db_name
      POSTGRES_USER        = var.db_event_username
      POSTGRES_SSLMODE     = "verify-full"
      POSTGRES_SSLROOTCERT = "/var/task/certs/eu-north-1-bundle.pem"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.pv_lambda,
    aws_iam_role_policy.pv_lambda,
    aws_vpc_endpoint.s3,
  ]

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_lambda_permission" "allow_s3_pv" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  statement_id   = "AllowElectionHubBucket"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.pv_processor[0].function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.documents.arn
  source_account = var.aws_account_id
}

resource "aws_s3_bucket_notification" "pv" {
  count = var.enable_new_resources && var.enable_pv_lambda ? 1 : 0

  bucket = aws_s3_bucket.documents.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.pv_processor[0].arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
  }

  depends_on = [aws_lambda_permission.allow_s3_pv]
}
