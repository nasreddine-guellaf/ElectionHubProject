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
