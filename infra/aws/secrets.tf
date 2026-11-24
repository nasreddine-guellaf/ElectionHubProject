resource "aws_secretsmanager_secret" "application_database" {
  count = var.enable_new_resources ? 1 : 0

  name                    = "electionhub/application/database"
  description             = "Non-owner ElectionHub runtime PostgreSQL credentials"
  recovery_window_in_days = 7

  tags = {
    Environment = "demo"
    Project     = "ElectionHub"
    Purpose     = "application-database"
  }

  lifecycle {
    prevent_destroy = true
  }
}
