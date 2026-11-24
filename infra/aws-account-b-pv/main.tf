terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "local" {
    path = "../../.local/aws-account-b/integrated-pv.tfstate"
  }
}

variable "aws_profile" {
  type    = string
  default = "electionhub-new-dev"
}

variable "account_a_vpc_id" {
  type = string
}

variable "account_a_rds_security_group_id" {
  type = string
}

variable "account_a_db_role_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:iam::749251635900:role/[A-Za-z0-9+=,.@_/-]+$", var.account_a_db_role_arn))
    error_message = "Use the dedicated database role ARN from Account A."
  }
}

variable "peering_active" {
  type        = bool
  default     = false
  description = "Set after reviewing and confirming Account A has accepted the peering request."
}

variable "sts_second_az" {
  type        = bool
  description = "Choose explicitly after reviewing the endpoint cost and availability."
}

provider "aws" {
  region              = "eu-north-1"
  profile             = var.aws_profile
  allowed_account_ids = ["865579549007"]
  default_tags {
    tags = {
      Project     = "ElectionHub"
      Environment = "account-b-integrated-pv"
    }
  }
}

locals {
  subnets = {
    "eun1-az1" = "10.41.10.0/24"
    "eun1-az2" = "10.41.11.0/24"
  }
  rds_cidrs   = ["10.40.10.0/24", "10.40.11.0/24"]
  reports_arn = "arn:aws:s3:::electionhub-demo-749251635900-eu-north-1/reports/*"
  rds_routes = {
    for pair in setproduct(keys(local.subnets), local.rds_cidrs) :
    "${pair[0]}:${pair[1]}" => { az = pair[0], cidr = pair[1] }
  }
}

resource "aws_vpc" "pv" {
  cidr_block           = "10.41.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}

resource "aws_subnet" "pv" {
  for_each                = local.subnets
  vpc_id                  = aws_vpc.pv.id
  availability_zone_id    = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = false
}

resource "aws_route_table" "pv" {
  for_each = local.subnets
  vpc_id   = aws_vpc.pv.id
}

resource "aws_route_table_association" "pv" {
  for_each       = local.subnets
  subnet_id      = aws_subnet.pv[each.key].id
  route_table_id = aws_route_table.pv[each.key].id
}

resource "aws_vpc_peering_connection" "account_a" {
  vpc_id        = aws_vpc.pv.id
  peer_vpc_id   = var.account_a_vpc_id
  peer_owner_id = "749251635900"
  auto_accept   = false
}

resource "aws_vpc_peering_connection_options" "account_a" {
  count                     = var.peering_active ? 1 : 0
  vpc_peering_connection_id = aws_vpc_peering_connection.account_a.id
  requester {
    allow_remote_vpc_dns_resolution = true
  }
}

resource "aws_route" "rds" {
  for_each                  = var.peering_active ? local.rds_routes : {}
  route_table_id            = aws_route_table.pv[each.value.az].id
  destination_cidr_block    = each.value.cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.account_a.id
}

resource "aws_security_group" "pv" {
  name        = "electionhub-b-pv"
  description = "Private integrated PV Lambda"
  vpc_id      = aws_vpc.pv.id
}

resource "aws_security_group" "sts" {
  name        = "electionhub-b-pv-sts"
  description = "Regional STS endpoint for PV"
  vpc_id      = aws_vpc.pv.id
}

resource "aws_vpc_security_group_egress_rule" "rds" {
  count                        = var.peering_active ? 1 : 0
  security_group_id            = aws_security_group.pv.id
  referenced_security_group_id = "749251635900/${var.account_a_rds_security_group_id}"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_egress_rule" "s3" {
  security_group_id = aws_security_group.pv.id
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "sts" {
  security_group_id            = aws_security_group.pv.id
  referenced_security_group_id = aws_security_group.sts.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

resource "aws_vpc_security_group_ingress_rule" "sts" {
  security_group_id            = aws_security_group.sts.id
  referenced_security_group_id = aws_security_group.pv.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

resource "aws_iam_role" "pv" {
  name = "electionhub-b-pv-role"
  path = "/electionhub/"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "qualification" {
  name = "electionhub-b-pv-qualification"
  role = aws_iam_role.pv.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = local.reports_arn },
      { Effect = "Allow", Action = "sts:AssumeRole", Resource = var.account_a_db_role_arn },
    ]
  })
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.pv.id
  service_name      = "com.amazonaws.eu-north-1.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for table in aws_route_table.pv : table.id]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = ["s3:GetObject", "s3:GetObjectVersion"]
      Resource  = local.reports_arn
      Condition = { ArnEquals = { "aws:PrincipalArn" = aws_iam_role.pv.arn } }
    }]
  })
}

resource "aws_vpc_endpoint" "sts" {
  vpc_id              = aws_vpc.pv.id
  service_name        = "com.amazonaws.eu-north-1.sts"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for az, subnet in aws_subnet.pv : subnet.id if var.sts_second_az || az == "eun1-az1"]
  security_group_ids  = [aws_security_group.sts.id]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.pv.arn }
      Action    = "sts:AssumeRole"
      Resource  = var.account_a_db_role_arn
    }]
  })
}

output "vpc_id" {
  value = aws_vpc.pv.id
}

output "peering_connection_id" {
  value = aws_vpc_peering_connection.account_a.id
}

output "lambda_security_group_id" {
  value = aws_security_group.pv.id
}

output "s3_gateway_endpoint_id" {
  value = aws_vpc_endpoint.s3.id
}

output "pv_execution_role_arn" {
  value = aws_iam_role.pv.arn
}
