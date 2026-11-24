locals {
  enabled   = var.enable_new_resources ? 1 : 0
  base_name = "${var.name_prefix}-${var.environment}"
  use_acr   = var.acr_resource_id != null
  tags = {
    project     = "electionhub"
    environment = var.environment
    phase       = "7"
    managed_by  = "terraform"
  }
}

resource "azurerm_resource_group" "web" {
  count    = local.enabled
  name     = "rg-${local.base_name}-web"
  location = var.location
  tags     = local.tags
}

resource "azurerm_log_analytics_workspace" "web" {
  count               = local.enabled
  name                = "log-${local.base_name}-web"
  location            = azurerm_resource_group.web[0].location
  resource_group_name = azurerm_resource_group.web[0].name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = local.tags
}

resource "azurerm_service_plan" "web" {
  count               = local.enabled
  name                = "plan-${local.base_name}-web"
  location            = azurerm_resource_group.web[0].location
  resource_group_name = azurerm_resource_group.web[0].name
  os_type             = "Linux"
  sku_name            = var.app_service_sku
  tags                = local.tags
}

# Un seul Web App conteneurisé : portail citoyen/agent et back-office partagent la même
# application React ; l'autorité d'accès reste FastAPI.
resource "azurerm_linux_web_app" "web" {
  count               = local.enabled
  name                = "app-${local.base_name}-web"
  location            = azurerm_resource_group.web[0].location
  resource_group_name = azurerm_resource_group.web[0].name
  service_plan_id     = azurerm_service_plan.web[0].id

  https_only                    = true
  public_network_access_enabled = true
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on                                     = true
    ftps_state                                    = "Disabled"
    minimum_tls_version                           = "1.2"
    http2_enabled                                 = true
    health_check_path                             = "/healthz"
    health_check_eviction_time_in_min             = 5
    container_registry_use_managed_identity       = local.use_acr
    container_registry_managed_identity_client_id = null

    application_stack {
      docker_registry_url = var.container_registry_url
      docker_image_name   = "${var.container_image_name}:${var.container_image_tag}"
    }
  }

  # Aucun secret ici : uniquement des paramètres non sensibles.
  app_settings = {
    WEBSITES_PORT                       = "8080"
    WEBSITES_ENABLE_APP_SERVICE_STORAGE = "false"
    API_UPSTREAM                        = var.api_upstream
    API_HOST_HEADER                     = var.api_host_header
  }

  logs {
    detailed_error_messages = false
    failed_request_tracing  = false

    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }
}

resource "azurerm_role_assignment" "acr_pull" {
  count                = local.enabled == 1 && local.use_acr ? 1 : 0
  scope                = var.acr_resource_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_linux_web_app.web[0].identity[0].principal_id
}

resource "azurerm_monitor_diagnostic_setting" "web" {
  count                      = local.enabled
  name                       = "diag-${local.base_name}-web"
  target_resource_id         = azurerm_linux_web_app.web[0].id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.web[0].id

  enabled_log {
    category = "AppServiceHTTPLogs"
  }

  enabled_log {
    category = "AppServiceConsoleLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
