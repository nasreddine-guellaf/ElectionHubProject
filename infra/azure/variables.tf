variable "subscription_id" {
  description = "Azure subscription ID. Required so a plan can never target another subscription."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "enable_new_resources" {
  description = "Safety switch. While false, the plan creates nothing. Set true only after explicit approval."
  type        = bool
  default     = false
}

variable "location" {
  description = "Azure region. To be confirmed with the project owner and the subscription's allowed regions."
  type        = string
  default     = "swedencentral"
}

variable "name_prefix" {
  description = "Prefix for resource names (lowercase letters, digits, hyphens)."
  type        = string
  default     = "electionhub"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,20}$", var.name_prefix))
    error_message = "name_prefix must be 3-20 characters: lowercase letters, digits, hyphens."
  }
}

variable "environment" {
  description = "Short environment label used in names and tags."
  type        = string
  default     = "demo"
}

variable "app_service_sku" {
  description = "App Service Plan SKU. B1 is the smallest Linux tier that supports custom containers reliably."
  type        = string
  default     = "B1"
}

variable "container_registry_url" {
  description = "Registry hosting the web image, e.g. https://myregistry.azurecr.io or https://ghcr.io."
  type        = string
  nullable    = false

  validation {
    condition     = startswith(var.container_registry_url, "https://")
    error_message = "container_registry_url must start with https://."
  }
}

variable "container_image_name" {
  description = "Image repository name without registry host, e.g. electionhub/web."
  type        = string
  default     = "electionhub/web"
}

variable "container_image_tag" {
  description = "Immutable image tag or digest-based tag. Avoid 'latest' for reproducible deployments."
  type        = string
  nullable    = false

  validation {
    condition     = var.container_image_tag != "latest"
    error_message = "Use an explicit version tag, not 'latest'."
  }
}

variable "acr_resource_id" {
  description = "Optional Azure Container Registry resource ID. When set, the web app identity receives AcrPull and pulls with managed identity."
  type        = string
  default     = null
}

variable "api_upstream" {
  description = "Stable HTTPS URL of the GCP API (no trailing path), e.g. https://api.example.org. Nginx proxies /api/ to it."
  type        = string
  nullable    = false

  validation {
    condition     = startswith(var.api_upstream, "https://")
    error_message = "api_upstream must be an https:// URL (TLS is verified by Nginx)."
  }
}

variable "api_host_header" {
  description = "Host header sent to the API. Normally the API hostname without scheme, e.g. api.example.org."
  type        = string
  nullable    = false
}

variable "log_retention_days" {
  description = "Log Analytics retention in days (30 is the minimum for the PerGB2018 SKU)."
  type        = number
  default     = 30
}
