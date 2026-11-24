resource "google_compute_global_address" "lb" {
  count      = local.enabled
  name       = "${local.name}-lb-ip"
  depends_on = [google_project_service.required]
}

# Certificat géré par Google : il n'est émis qu'une fois l'enregistrement DNS A du domaine
# pointé vers l'IP du load balancer (sortie lb_ip_address).
resource "google_compute_managed_ssl_certificate" "api" {
  count = local.enabled
  name  = "${local.name}-api-cert"

  managed {
    domains = [var.domain]
  }
}

resource "google_compute_backend_service" "api" {
  count                 = local.enabled
  name                  = "${local.name}-api-backend"
  protocol              = "HTTP"
  port_name             = "http-api"
  load_balancing_scheme = "EXTERNAL"
  timeout_sec           = 30
  health_checks         = [google_compute_health_check.readiness[0].id]

  backend {
    group           = google_compute_region_instance_group_manager.api[0].instance_group
    balancing_mode  = "UTILIZATION"
    max_utilization = 0.8
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_url_map" "https" {
  count           = local.enabled
  name            = "${local.name}-https-map"
  default_service = google_compute_backend_service.api[0].id
}

resource "google_compute_target_https_proxy" "api" {
  count            = local.enabled
  name             = "${local.name}-https-proxy"
  url_map          = google_compute_url_map.https[0].id
  ssl_certificates = [google_compute_managed_ssl_certificate.api[0].id]
  ssl_policy       = google_compute_ssl_policy.modern[0].id
}

resource "google_compute_ssl_policy" "modern" {
  count           = local.enabled
  name            = "${local.name}-tls12"
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
}

resource "google_compute_global_forwarding_rule" "https" {
  count                 = local.enabled
  name                  = "${local.name}-https"
  ip_address            = google_compute_global_address.lb[0].address
  port_range            = "443"
  target                = google_compute_target_https_proxy.api[0].id
  load_balancing_scheme = "EXTERNAL"
}

# HTTP clair : uniquement une redirection 301 vers HTTPS.
resource "google_compute_url_map" "redirect" {
  count = local.enabled
  name  = "${local.name}-http-redirect"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  count   = local.enabled
  name    = "${local.name}-http-proxy"
  url_map = google_compute_url_map.redirect[0].id
}

resource "google_compute_global_forwarding_rule" "http" {
  count                 = local.enabled
  name                  = "${local.name}-http"
  ip_address            = google_compute_global_address.lb[0].address
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect[0].id
  load_balancing_scheme = "EXTERNAL"
}
