data "aws_ssm_parameter" "amazon_linux_2023_arm64" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "test_runner" {
  count = var.enable_new_resources && var.enable_test_runner ? 1 : 0

  ami                         = data.aws_ssm_parameter.amazon_linux_2023_arm64[0].value
  instance_type               = var.test_runner_instance_type
  subnet_id                   = aws_subnet.runner[0].id
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.runner[0].id]
  iam_instance_profile        = aws_iam_instance_profile.test_runner[0].name

  instance_initiated_shutdown_behavior = "terminate"
  user_data_replace_on_change          = true
  user_data = templatefile("${path.module}/runner/user_data.sh.tftpl", {
    ttl_minutes = var.test_runner_ttl_hours * 60
  })

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
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

  tags = {
    Name              = "electionhub-test-runner"
    Environment       = "demo"
    Project           = "ElectionHub"
    Temporary         = "true"
    ExpiresAfterHours = tostring(var.test_runner_ttl_hours)
  }

  depends_on = [
    aws_route.runner_internet,
    aws_route_table_association.runner,
    aws_iam_role_policy.test_runner_database,
    aws_iam_role_policy_attachment.test_runner_ssm,
  ]
}
