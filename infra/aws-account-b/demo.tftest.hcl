mock_provider "aws" {}

variables {
  account_b_id = "000000000001"
  aws_profile  = "offline-mock"
}

run "demo_plan" {
  command = plan

  assert {
    condition     = aws_lambda_function.demo["pv"].handler == "app.lambda_pv_demo.lambda_handler"
    error_message = "The PV demo must use synthetic dependencies."
  }

  assert {
    condition     = aws_lambda_function.demo["otp"].environment[0].variables.OTP_DELIVERY_MODE == "mock"
    error_message = "The OTP demo must run in mock mode."
  }

  assert {
    condition = alltrue([
      for function in values(aws_lambda_function.demo) : function.reserved_concurrent_executions == 1
    ])
    error_message = "Each demo function must be limited to one concurrent execution."
  }

  assert {
    condition     = aws_sqs_queue.pv_dlq.sqs_managed_sse_enabled
    error_message = "The PV dead-letter queue must use SQS-managed encryption."
  }
}
