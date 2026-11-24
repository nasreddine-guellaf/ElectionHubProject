variable "enable_backup_api" {
  type    = bool
  default = false

  validation {
    condition     = !var.enable_backup_api || var.enable_new_resources
    error_message = "The backup API requires enable_new_resources=true."
  }
}

variable "backup_api_commit" {
  type        = string
  default     = ""
  description = "Reviewed, publicly fetchable ElectionHub commit for the backup API."

  validation {
    condition     = !var.enable_backup_api || can(regex("^[a-f0-9]{40}$", var.backup_api_commit))
    error_message = "Supply a full Git commit SHA when enabling the backup API."
  }
}

locals {
  backup_count = var.enable_new_resources && var.enable_backup_api ? 1 : 0
  backup_tags  = { Name = "electionhub-backup-api", Project = "ElectionHub", Environment = "demo" }
}

resource "aws_subnet" "backup_api" {
  count             = local.backup_count
  vpc_id            = aws_vpc.electionhub[0].id
  availability_zone = data.aws_availability_zones.available.names[0]
  cidr_block        = cidrsubnet(aws_vpc.electionhub[0].cidr_block, 8, 30)
  tags              = local.backup_tags
}

resource "aws_route_table" "backup_api" {
  count  = local.backup_count
  vpc_id = aws_vpc.electionhub[0].id
  tags   = local.backup_tags
}

resource "aws_route" "backup_api_https" {
  count                  = local.backup_count
  route_table_id         = aws_route_table.backup_api[0].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.electionhub[0].id
}

resource "aws_route_table_association" "backup_api" {
  count          = local.backup_count
  route_table_id = aws_route_table.backup_api[0].id
  subnet_id      = aws_subnet.backup_api[0].id
}

resource "aws_security_group" "backup_api" {
  count       = local.backup_count
  name        = "electionhub-backup-api"
  description = "SSM-managed backup API with no inbound rules"
  vpc_id      = aws_vpc.electionhub[0].id
  ingress     = []
  tags        = local.backup_tags
}

resource "aws_vpc_security_group_egress_rule" "backup_api_https" {
  count             = local.backup_count
  security_group_id = aws_security_group.backup_api[0].id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "backup_api_postgres" {
  count                        = local.backup_count
  security_group_id            = aws_security_group.backup_api[0].id
  referenced_security_group_id = aws_security_group.postgres[0].id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_backup_api" {
  count                        = local.backup_count
  security_group_id            = aws_security_group.postgres[0].id
  referenced_security_group_id = aws_security_group.backup_api[0].id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_iam_role" "backup_api" {
  count              = local.backup_count
  name               = "ElectionHubBackupApiRole"
  path               = "/electionhub/"
  assume_role_policy = data.aws_iam_policy_document.test_runner_trust.json
  tags               = local.backup_tags
}

resource "aws_iam_role_policy" "backup_api_s3" {
  count  = local.backup_count
  name   = "ElectionHubBackupApiObjects"
  role   = aws_iam_role.backup_api[0].id
  policy = data.aws_iam_policy_document.application_s3.json
}

resource "aws_iam_role_policy" "backup_api_secret" {
  count = local.backup_count
  name  = "ElectionHubBackupApiDatabase"
  role  = aws_iam_role.backup_api[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = aws_secretsmanager_secret.application_database[0].arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "backup_api_ssm" {
  count      = local.backup_count
  role       = aws_iam_role.backup_api[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "backup_api" {
  count = local.backup_count
  name  = "ElectionHubBackupApi"
  path  = "/electionhub/"
  role  = aws_iam_role.backup_api[0].name
}

resource "aws_instance" "backup_api" {
  count                       = local.backup_count
  ami                         = data.aws_ssm_parameter.amazon_linux_2023_arm64[0].value
  instance_type               = "t4g.micro"
  subnet_id                   = aws_subnet.backup_api[0].id
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.backup_api[0].id]
  iam_instance_profile        = aws_iam_instance_profile.backup_api[0].name
  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/backup/user_data.sh.tftpl", {
    commit     = var.backup_api_commit
    region     = var.aws_region
    bucket     = aws_s3_bucket.documents.bucket
    secret_arn = aws_secretsmanager_secret.application_database[0].arn
  })

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    encrypted             = true
    delete_on_termination = true
    volume_type           = "gp3"
    volume_size           = 8
  }

  credit_specification {
    cpu_credits = "standard"
  }

  tags = local.backup_tags
  depends_on = [
    aws_iam_role_policy.backup_api_s3,
    aws_iam_role_policy.backup_api_secret,
    aws_iam_role_policy_attachment.backup_api_ssm,
    aws_route.backup_api_https,
    aws_route_table_association.backup_api,
    aws_vpc_security_group_ingress_rule.postgres_from_backup_api,
  ]
}

output "backup_api_instance_id" {
  value = try(aws_instance.backup_api[0].id, null)
}
