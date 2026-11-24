data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "electionhub" {
  count = var.enable_new_resources ? 1 : 0

  cidr_block           = "10.40.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "electionhub-demo"
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_internet_gateway" "electionhub" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  vpc_id = aws_vpc.electionhub[0].id

  tags = {
    Name        = "electionhub-demo"
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_subnet" "database" {
  count = var.enable_new_resources ? 2 : 0

  vpc_id                  = aws_vpc.electionhub[0].id
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(aws_vpc.electionhub[0].cidr_block, 8, count.index + 10)
  map_public_ip_on_launch = false

  tags = {
    Name        = "electionhub-db-${count.index + 1}"
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_route_table" "database" {
  count = var.enable_new_resources ? 1 : 0

  vpc_id = aws_vpc.electionhub[0].id

  tags = {
    Name        = "electionhub-db"
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_route_table_association" "database" {
  count = var.enable_new_resources ? 2 : 0

  subnet_id      = aws_subnet.database[count.index].id
  route_table_id = aws_route_table.database[0].id
}

resource "aws_subnet" "runner" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  vpc_id                  = aws_vpc.electionhub[0].id
  availability_zone       = data.aws_availability_zones.available.names[0]
  cidr_block              = cidrsubnet(aws_vpc.electionhub[0].cidr_block, 8, 20)
  map_public_ip_on_launch = true

  tags = {
    Name        = "electionhub-runner"
    Environment = "demo"
    Project     = "ElectionHub"
    Temporary   = "true"
  }
}

resource "aws_route_table" "runner" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  vpc_id = aws_vpc.electionhub[0].id

  tags = {
    Name        = "electionhub-runner"
    Environment = "demo"
    Project     = "ElectionHub"
    Temporary   = "true"
  }
}

resource "aws_route" "runner_internet" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  route_table_id         = aws_route_table.runner[0].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.electionhub[0].id
}

resource "aws_route_table_association" "runner" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  subnet_id      = aws_subnet.runner[0].id
  route_table_id = aws_route_table.runner[0].id
}

resource "aws_security_group" "postgres" {
  count = var.enable_new_resources ? 1 : 0

  name        = "electionhub-postgres"
  description = "Restricted PostgreSQL ingress for ElectionHub"
  vpc_id      = aws_vpc.electionhub[0].id
  egress      = []

  tags = {
    Name        = "electionhub-postgres"
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_security_group" "runner" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  name        = "electionhub-test-runner"
  description = "No inbound access; outbound is limited to HTTPS and PostgreSQL"
  vpc_id      = aws_vpc.electionhub[0].id
  ingress     = []
  egress      = []

  tags = {
    Name        = "electionhub-test-runner"
    Environment = "demo"
    Project     = "ElectionHub"
    Temporary   = "true"
  }
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_runner" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  security_group_id            = aws_security_group.postgres[0].id
  description                  = "PostgreSQL only from the temporary migration runner"
  referenced_security_group_id = aws_security_group.runner[0].id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "runner_https" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  security_group_id = aws_security_group.runner[0].id
  description       = "HTTPS for SSM, package installation, Git, and the AWS RDS CA bundle"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "runner_postgres" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  security_group_id            = aws_security_group.runner[0].id
  description                  = "PostgreSQL only to the ElectionHub RDS security group"
  referenced_security_group_id = aws_security_group.postgres[0].id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}
