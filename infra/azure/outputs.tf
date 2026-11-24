output "web_app_hostname" {
  description = "Default HTTPS hostname of the single web app (null while enable_new_resources is false)."
  value       = one(azurerm_linux_web_app.web[*].default_hostname)
}

output "web_app_principal_id" {
  description = "Managed identity principal ID, to grant AcrPull manually if acr_resource_id was not provided."
  value       = one(azurerm_linux_web_app.web[*].identity[0].principal_id)
}

output "resource_group_name" {
  description = "Resource group to delete for a full cleanup."
  value       = one(azurerm_resource_group.web[*].name)
}
