mock_provider "aws" {}

variables {
  account_a_vpc_id                = "vpc-0123456789abcdef0"
  account_a_rds_security_group_id = "sg-0123456789abcdef0"
  account_a_db_role_arn           = "arn:aws:iam::749251635900:role/electionhub-pv-rds"
  sts_second_az                   = false
}

run "peering_request" {
  command = plan

  assert {
    condition     = aws_vpc.pv.cidr_block == "10.41.0.0/16" && length(aws_subnet.pv) == 2
    error_message = "The private network must use the reviewed B VPC and two subnets."
  }

  assert {
    condition     = length(aws_route.rds) == 0 && length(aws_vpc_security_group_egress_rule.rds) == 0
    error_message = "RDS routes and egress must wait for peering acceptance."
  }
}

run "accepted_peering" {
  command = plan

  variables {
    peering_active = true
    sts_second_az  = true
  }

  assert {
    condition     = length(aws_route.rds) == 4 && length(aws_vpc_security_group_egress_rule.rds) == 1
    error_message = "Route both B subnet tables to both A RDS subnets and limit PostgreSQL egress."
  }
}

run "private_runtime" {
  command = plan

  variables {
    peering_active         = true
    enable_pv_runtime      = true
    account_a_rds_hostname = "electionhub-test.abcdefghijk.eu-north-1.rds.amazonaws.com"
  }

  assert {
    condition = (
      aws_lambda_function.pv_runtime[0].handler == "app.lambda_pv.lambda_handler" &&
      aws_lambda_function.pv_runtime[0].environment[0].variables.PV_REQUIRE_VERSION == "true" &&
      aws_lambda_function.pv_runtime[0].environment[0].variables.PV_RDS_ASSUME_ROLE_ARN == var.account_a_db_role_arn
    )
    error_message = "The integrated handler must require a version and assume the exact RDS role."
  }
}

run "private_runtime_from_s3" {
  command = plan

  variables {
    peering_active          = true
    enable_pv_runtime       = true
    pv_reserved_concurrency = -1
    account_a_rds_hostname  = "electionhub-test.abcdefghijk.eu-north-1.rds.amazonaws.com"
    pv_runtime_s3 = {
      bucket     = "electionhub-b-test-artifacts"
      key        = "pv/lambda_pv.zip"
      version_id = "test-package-version"
    }
  }

  assert {
    condition = (
      aws_lambda_function.pv_runtime[0].reserved_concurrent_executions == -1 &&
      aws_lambda_function.pv_runtime[0].filename == null &&
      aws_lambda_function.pv_runtime[0].s3_bucket == var.pv_runtime_s3.bucket &&
      aws_lambda_function.pv_runtime[0].s3_key == var.pv_runtime_s3.key &&
      aws_lambda_function.pv_runtime[0].s3_object_version == var.pv_runtime_s3.version_id
    )
    error_message = "Lambda must load the exact staged artifact without uploading the local ZIP."
  }
}
