terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "local" {
    path = "../../.local/aws-account-b/demo.tfstate"
  }
}

variable "account_b_id" {
  type        = string
  description = "Verified 12-digit Account B ID."
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_b_id))
    error_message = "Supply the verified 12-digit Account B ID."
  }
}

variable "aws_profile" {
  type        = string
  description = "Named Account B profile backed by temporary credentials."
  validation {
    condition     = trimspace(var.aws_profile) != ""
    error_message = "Supply a named Account B profile."
  }
}

variable "aws_region" {
  type        = string
  default     = "eu-north-1"
  description = "Demo region. Future direct S3 delivery requires eu-north-1."
}

provider "aws" {
  region              = var.aws_region
  profile             = var.aws_profile
  allowed_account_ids = [var.account_b_id]

  default_tags {
    tags = {
      Project     = "ElectionHub"
      Environment = "account-b-demo"
    }
  }
}

locals {
  functions = {
    pv = {
      name    = "electionhub-b-demo-pv"
      handler = "app.lambda_pv_demo.lambda_handler"
      timeout = 10
    }
    otp = {
      name    = "electionhub-b-demo-otp"
      handler = "app.lambda_otp.lambda_handler"
      timeout = 8
    }
  }
}

resource "aws_cloudwatch_log_group" "function" {
  for_each          = local.functions
  name              = "/aws/lambda/${each.value.name}"
  retention_in_days = 14
}

resource "aws_sqs_queue" "pv_dlq" {
  name                      = "electionhub-b-demo-pv-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_iam_role" "function" {
  for_each = local.functions
  name     = "${each.value.name}-role"
  path     = "/electionhub/"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "function" {
  for_each = local.functions
  name     = "${each.value.name}-execution"
  role     = aws_iam_role.function[each.key].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.function[each.key].arn}:log-stream:*"]
      }],
      each.key == "pv" ? [{
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = [aws_sqs_queue.pv_dlq.arn]
      }] : []
    )
  })
}

resource "aws_lambda_function" "demo" {
  for_each         = local.functions
  function_name    = each.value.name
  role             = aws_iam_role.function[each.key].arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = each.value.handler
  filename         = "${path.module}/../../.local/build/account_b_${each.key}.zip"
  source_code_hash = filebase64sha256("${path.module}/../../.local/build/account_b_${each.key}.zip")

  memory_size                    = 128
  timeout                        = each.value.timeout
  reserved_concurrent_executions = 1

  environment {
    variables = each.key == "otp" ? { OTP_DELIVERY_MODE = "mock" } : {}
  }

  dynamic "dead_letter_config" {
    for_each = each.key == "pv" ? [aws_sqs_queue.pv_dlq.arn] : []
    content {
      target_arn = dead_letter_config.value
    }
  }

  depends_on = [aws_iam_role_policy.function]
}

resource "aws_lambda_function_event_invoke_config" "pv" {
  function_name                = aws_lambda_function.demo["pv"].function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 900
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  for_each            = local.functions
  alarm_name          = "${each.value.name}-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value.name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "pv_dlq" {
  alarm_name          = "electionhub-b-demo-pv-dlq-visible"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.pv_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

output "function_arns" {
  value = { for key, function in aws_lambda_function.demo : key => function.arn }
}

output "execution_role_arns" {
  value = { for key, role in aws_iam_role.function : key => role.arn }
}
