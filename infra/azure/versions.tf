terraform {
  required_version = ">= 1.5, < 2.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.0, < 5.0"
    }
  }
}

provider "azurerm" {
  features {}

  subscription_id = var.subscription_id
  # Pas d'enregistrement automatique de fournisseurs de ressources : action explicite uniquement.
  resource_provider_registrations = "none"
}
