# Liveness (auto-réparation) : ne dépend pas de la base. Un RDS indisponible ne doit pas
# provoquer la recréation en boucle de toutes les instances.
resource "google_compute_health_check" "liveness" {
  count               = local.enabled
  name                = "${local.name}-liveness"
  check_interval_sec  = 15
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 4

  http_health_check {
    port         = local.api_port
    request_path = "/openapi.json"
  }

  depends_on = [google_project_service.required]
}

# Readiness (load balancer) : /health vérifie la base et la version de migration, donc une
# instance sans schéma migré ne reçoit pas de trafic.
resource "google_compute_health_check" "readiness" {
  count               = local.enabled
  name                = "${local.name}-readiness"
  check_interval_sec  = 10
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = local.api_port
    request_path = "/health"
  }

  depends_on = [google_project_service.required]
}

resource "google_compute_instance_template" "api" {
  count        = local.enabled
  name_prefix  = "${local.name}-api-"
  machine_type = var.machine_type
  region       = var.region
  tags         = ["${local.name}-api"]
  labels       = local.labels

  disk {
    source_image = "projects/debian-cloud/global/images/family/debian-12"
    auto_delete  = true
    boot         = true
    disk_size_gb = 20
    disk_type    = "pd-balanced"
  }

  # Aucune IP publique : la sortie passe par Cloud NAT (IPv4 fixe).
  network_interface {
    subnetwork = google_compute_subnetwork.api[0].id
  }

  service_account {
    email  = google_service_account.api[0].email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
    startup-script = templatefile("${path.module}/startup/startup.sh.tftpl", {
      project_id            = var.project_id
      region                = var.region
      image                 = local.image
      password_secret       = google_secret_manager_secret.postgres_password[0].secret_id
      ca_secret             = google_secret_manager_secret.rds_ca_bundle[0].secret_id
      postgres_host         = var.rds_host
      postgres_port         = var.rds_port
      postgres_db           = var.postgres_db
      postgres_user         = var.postgres_user
      postgres_pool_size    = var.postgres_pool_size
      postgres_max_overflow = var.postgres_max_overflow
      api_workers           = var.api_workers
      aws_region            = var.aws_region
      s3_bucket             = var.s3_bucket
      aws_role_arn          = var.aws_role_arn
      aws_token_audience    = var.aws_token_audience
      api_port              = local.api_port
    })
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_compute_region_instance_group_manager" "api" {
  count              = local.enabled
  name               = "${local.name}-api-mig"
  region             = var.region
  base_instance_name = "${local.name}-api"

  version {
    instance_template = google_compute_instance_template.api[0].self_link_unique
  }

  named_port {
    name = "http-api"
    port = local.api_port
  }

  auto_healing_policies {
    health_check      = google_compute_health_check.liveness[0].id
    initial_delay_sec = 300
  }

  update_policy {
    type                         = "PROACTIVE"
    minimal_action               = "REPLACE"
    max_surge_fixed              = 3
    max_unavailable_fixed        = 0
    replacement_method           = "SUBSTITUTE"
    instance_redistribution_type = "PROACTIVE"
  }
}

resource "google_compute_region_autoscaler" "api" {
  count  = local.enabled
  name   = "${local.name}-api-autoscaler"
  region = var.region
  target = google_compute_region_instance_group_manager.api[0].id

  autoscaling_policy {
    min_replicas    = var.min_replicas
    max_replicas    = var.max_replicas
    cooldown_period = 120

    cpu_utilization {
      target = 0.6
    }
  }
}
