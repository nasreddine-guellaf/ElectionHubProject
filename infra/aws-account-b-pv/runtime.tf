variable "enable_pv_runtime" {
  type    = bool
  default = false
}

variable "pv_reserved_concurrency" {
  type        = number
  default     = 2
  description = "Use -1 for manual qualification when the account has no reservable slots."

  validation {
    condition     = contains([-1, 2], var.pv_reserved_concurrency)
    error_message = "Use 2 for normal operation or -1 to use the shared pool during manual qualification."
  }
}

variable "account_a_rds_hostname" {
  type    = string
  default = ""
}

variable "account_a_rds_database" {
  type    = string
  default = "electionhub"
}

variable "pv_runtime_s3" {
  type = object({
    bucket     = string
    key        = string
    version_id = string
  })
  default = null

  validation {
    condition = var.pv_runtime_s3 == null ? true : (
      trimspace(var.pv_runtime_s3.bucket) != "" &&
      var.pv_runtime_s3.bucket != "electionhub-demo-749251635900-eu-north-1" &&
      trimspace(var.pv_runtime_s3.key) != "" &&
      trimspace(var.pv_runtime_s3.version_id) != "" &&
      var.pv_runtime_s3.version_id != "null"
    )
    error_message = "Provide an Account B artifact bucket, key, and exact version. The Account A documents bucket is reserved for reports."
  }
}

locals {
  pv_function_name = "electionhub-b-pv"
  pv_function_arn  = "arn:aws:lambda:eu-north-1:865579549007:function:${local.pv_function_name}"
  pv_runtime_zip   = "${path.module}/../../.local/build/lambda_pv.zip"
  eni_actions = [
    "ec2:CreateNetworkInterface",
    "ec2:DescribeNetworkInterfaces",
    "ec2:DescribeSubnets",
    "ec2:DeleteNetworkInterface",
    "ec2:AssignPrivateIpAddresses",
    "ec2:UnassignPrivateIpAddresses",
  ]
}

resource "aws_cloudwatch_log_group" "pv_runtime" {
  count             = var.enable_pv_runtime ? 1 : 0
  name              = "/aws/lambda/${local.pv_function_name}"
  retention_in_days = 14
}

resource "aws_sqs_queue" "pv_runtime_dlq" {
  count                     = var.enable_pv_runtime ? 1 : 0
  name                      = "electionhub-b-pv-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_iam_role_policy" "pv_runtime" {
  count = var.enable_pv_runtime ? 1 : 0
  name  = "electionhub-b-pv-runtime"
  role  = aws_iam_role.pv.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = "${aws_cloudwatch_log_group.pv_runtime[0].arn}:log-stream:*"
      },
      { Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.pv_runtime_dlq[0].arn },
      { Effect = "Allow", Action = local.eni_actions, Resource = "*" },
      {
        Effect    = "Deny", Action = local.eni_actions, Resource = "*",
        Condition = { ArnEquals = { "lambda:SourceFunctionArn" = local.pv_function_arn } }
      }
    ]
  })
}

resource "aws_lambda_function" "pv_runtime" {
  count                          = var.enable_pv_runtime ? 1 : 0
  function_name                  = local.pv_function_name
  role                           = aws_iam_role.pv.arn
  runtime                        = "python3.11"
  architectures                  = ["x86_64"]
  handler                        = "app.lambda_pv.lambda_handler"
  filename                       = var.pv_runtime_s3 == null ? local.pv_runtime_zip : null
  s3_bucket                      = try(var.pv_runtime_s3.bucket, null)
  s3_key                         = try(var.pv_runtime_s3.key, null)
  s3_object_version              = try(var.pv_runtime_s3.version_id, null)
  source_code_hash               = filebase64sha256(local.pv_runtime_zip)
  memory_size                    = 256
  timeout                        = 60
  reserved_concurrent_executions = var.pv_reserved_concurrency

  lifecycle {
    precondition {
      condition = var.peering_active && can(regex(
        "^[a-z0-9][a-z0-9.-]+[.]eu-north-1[.]rds[.]amazonaws[.]com$",
        var.account_a_rds_hostname
      )) && trimspace(var.account_a_rds_database) != ""
      error_message = "Enable the active peering routes and supply the original Stockholm RDS hostname and database name."
    }
  }

  vpc_config {
    subnet_ids         = [for subnet in aws_subnet.pv : subnet.id]
    security_group_ids = [aws_security_group.pv.id]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.pv_runtime_dlq[0].arn
  }

  environment {
    variables = {
      S3_BUCKET              = "electionhub-demo-749251635900-eu-north-1"
      PV_REQUIRE_VERSION     = "true"
      PV_RDS_ASSUME_ROLE_ARN = var.account_a_db_role_arn
      POSTGRES_HOST          = var.account_a_rds_hostname
      POSTGRES_PORT          = "5432"
      POSTGRES_DB            = var.account_a_rds_database
      POSTGRES_USER          = "electionhub_event_processor"
      POSTGRES_SSLROOTCERT   = "/var/task/certs/eu-north-1-bundle.pem"
    }
  }

  depends_on = [
    aws_iam_role_policy.pv_runtime,
    aws_iam_role_policy.qualification,
  ]
}

resource "aws_lambda_function_event_invoke_config" "pv_runtime" {
  count                        = var.enable_pv_runtime ? 1 : 0
  function_name                = aws_lambda_function.pv_runtime[0].function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 900
}

output "pv_runtime_function_arn" {
  value = one(aws_lambda_function.pv_runtime[*].arn)
}
