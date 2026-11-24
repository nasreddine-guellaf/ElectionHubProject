locals {
  enabled        = var.enable_new_resources ? 1 : 0
  name           = var.name_prefix
  repo_id        = "${local.name}-images"
  image          = "${var.region}-docker.pkg.dev/${var.project_id}/${local.repo_id}/api:${var.api_image_tag}"
  health_ranges  = ["130.211.0.0/22", "35.191.0.0/16"] # sondes Google Cloud Load Balancing
  iap_ssh_range  = "35.235.240.0/20"
  required_apis  = ["compute.googleapis.com", "artifactregistry.googleapis.com", "secretmanager.googleapis.com", "iam.googleapis.com", "logging.googleapis.com", "monitoring.googleapis.com"]
  labels         = { project = "electionhub", phase = "6", managed_by = "terraform" }
  api_port       = 8000
  max_connection = var.max_replicas * var.api_workers * (var.postgres_pool_size + var.postgres_max_overflow)
}

resource "google_project_service" "required" {
  for_each           = var.enable_new_resources ? toset(local.required_apis) : toset([])
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- Registre d'images

resource "google_artifact_registry_repository" "images" {
  count         = local.enabled
  location      = var.region
  repository_id = local.repo_id
  format        = "DOCKER"
  description   = "Images ElectionHub (API)"
  labels        = local.labels
  depends_on    = [google_project_service.required]
}

# ---------------------------------------------------------------- Identité et secrets

resource "google_service_account" "api" {
  count        = local.enabled
  account_id   = "${local.name}-api"
  display_name = "ElectionHub API instances (least privilege)"
  depends_on   = [google_project_service.required]
}

# Les conteneurs secrets sont créés vides : aucune valeur n'est jamais écrite par Terraform.
# Le mot de passe SQL et le bundle CA RDS sont ajoutés hors Terraform (voir README).
resource "google_secret_manager_secret" "postgres_password" {
  count     = local.enabled
  secret_id = "${local.name}-postgres-password"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "rds_ca_bundle" {
  count     = local.enabled
  secret_id = "${local.name}-rds-ca-bundle"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "password_reader" {
  count     = local.enabled
  secret_id = google_secret_manager_secret.postgres_password[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_secret_manager_secret_iam_member" "ca_reader" {
  count     = local.enabled
  secret_id = google_secret_manager_secret.rds_ca_bundle[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_artifact_registry_repository_iam_member" "image_reader" {
  count      = local.enabled
  location   = var.region
  repository = google_artifact_registry_repository.images[0].name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_project_iam_member" "logging" {
  count   = local.enabled
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.api[0].email}"
}

resource "google_project_iam_member" "monitoring" {
  count   = local.enabled
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.api[0].email}"
}

# ---------------------------------------------------------------- Réseau et sortie stable

resource "google_compute_network" "vpc" {
  count                   = local.enabled
  name                    = "${local.name}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.required]
}

resource "google_compute_subnetwork" "api" {
  count                    = local.enabled
  name                     = "${local.name}-api"
  region                   = var.region
  network                  = google_compute_network.vpc[0].id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

# IPv4 de sortie fixe : seule adresse à autoriser (en /32) dans le groupe de sécurité RDS
# si la connexion inter-cloud passe par l'endpoint public filtré.
resource "google_compute_address" "nat_egress" {
  count        = local.enabled
  name         = "${local.name}-nat-egress"
  region       = var.region
  address_type = "EXTERNAL"
  depends_on   = [google_project_service.required]
}

resource "google_compute_router" "nat" {
  count   = local.enabled
  name    = "${local.name}-router"
  region  = var.region
  network = google_compute_network.vpc[0].id
}

resource "google_compute_router_nat" "nat" {
  count                              = local.enabled
  name                               = "${local.name}-nat"
  router                             = google_compute_router.nat[0].name
  region                             = var.region
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.nat_egress[0].self_link]
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.api[0].id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

resource "google_compute_firewall" "health_checks" {
  count         = local.enabled
  name          = "${local.name}-allow-health-checks"
  network       = google_compute_network.vpc[0].name
  direction     = "INGRESS"
  source_ranges = local.health_ranges
  target_tags   = ["${local.name}-api"]

  allow {
    protocol = "tcp"
    ports    = [tostring(local.api_port)]
  }
}

resource "google_compute_firewall" "iap_ssh" {
  count         = local.enabled == 1 && var.allow_iap_ssh ? 1 : 0
  name          = "${local.name}-allow-iap-ssh"
  network       = google_compute_network.vpc[0].name
  direction     = "INGRESS"
  source_ranges = [local.iap_ssh_range]
  target_tags   = ["${local.name}-api"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
