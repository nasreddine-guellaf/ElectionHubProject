resource "aws_db_subnet_group" "electionhub" {
  count = var.enable_new_resources ? 1 : 0

  name       = "electionhub-demo"
  subnet_ids = aws_subnet.database[*].id

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_db_parameter_group" "postgres16" {
  count = var.enable_new_resources ? 1 : 0

  name   = "electionhub-postgres16"
  family = "postgres16"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
  }
}

resource "aws_db_instance" "electionhub" {
  count = var.enable_new_resources ? 1 : 0

  identifier     = "electionhub-demo"
  engine         = "postgres"
  engine_version = var.rds_engine_version
  instance_class = var.rds_instance_class

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name                             = var.db_name
  username                            = var.db_master_username
  manage_master_user_password         = true
  iam_database_authentication_enabled = true
  port                                = 5432

  db_subnet_group_name   = aws_db_subnet_group.electionhub[0].name
  parameter_group_name   = aws_db_parameter_group.postgres16[0].name
  vpc_security_group_ids = [aws_security_group.postgres[0].id]
  publicly_accessible    = false
  network_type           = "IPV4"

  multi_az                   = false
  auto_minor_version_upgrade = true
  apply_immediately          = false
  ca_cert_identifier         = "rds-ca-rsa2048-g1"

  backup_retention_period = var.rds_backup_retention_days
  backup_window           = "02:00-03:00"
  maintenance_window      = "sun:03:30-sun:04:30"
  copy_tags_to_snapshot   = true

  monitoring_interval          = 0
  performance_insights_enabled = false

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "electionhub-demo-final"

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
  }

  lifecycle {
    prevent_destroy = true
  }
}
