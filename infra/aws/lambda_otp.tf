variable "enable_otp_lambda" {
  description = "Deploys the Account A mock OTP transport after the demo infrastructure is enabled."
  type        = bool
  default     = false

  validation {
    condition     = !var.enable_otp_lambda || var.enable_new_resources
    error_message = "enable_otp_lambda requires enable_new_resources=true."
  }
}

locals {
  otp_lambda_name    = "electionhub-otp"
  otp_lambda_package = "${path.module}/../../.local/build/account-a-otp.zip"
}

resource "aws_cloudwatch_log_group" "otp_lambda" {
  count             = var.enable_otp_lambda ? 1 : 0
  name              = "/aws/lambda/${local.otp_lambda_name}"
  retention_in_days = 7
}

resource "aws_iam_role" "otp_lambda" {
  count = var.enable_otp_lambda ? 1 : 0
  name  = "ElectionHubOtpLambdaRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "otp_lambda_logs" {
  count = var.enable_otp_lambda ? 1 : 0
  name  = "ElectionHubOtpLambdaLogs"
  role  = aws_iam_role.otp_lambda[0].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.otp_lambda[0].arn}:log-stream:*"
    }]
  })
}

resource "aws_lambda_function" "otp" {
  count = var.enable_otp_lambda ? 1 : 0

  function_name                  = local.otp_lambda_name
  role                           = aws_iam_role.otp_lambda[0].arn
  handler                        = "lambda_otp.lambda_handler"
  runtime                        = "python3.12"
  filename                       = local.otp_lambda_package
  source_code_hash               = filebase64sha256(local.otp_lambda_package)
  memory_size                    = 128
  timeout                        = 8
  reserved_concurrent_executions = 2

  environment {
    variables = { OTP_DELIVERY_MODE = "mock" }
  }

  depends_on = [aws_iam_role_policy.otp_lambda_logs]
}
