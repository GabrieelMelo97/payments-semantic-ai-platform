output "raw_bucket_name" {
  value       = module.storage.bucket_name
  description = "GCS raw data bucket."
}

output "bigquery_datasets" {
  value       = module.warehouse.dataset_ids
  description = "Provisioned BigQuery datasets."
}

output "service_accounts" {
  value       = module.security.service_accounts
  description = "Least-privilege Service Accounts."
}

output "artifact_registry_url" {
  value       = module.compute.artifact_registry_url
  description = "Artifact Registry Docker repository URL."
}

output "copilot_service_uri" {
  value       = module.compute.copilot_service_uri
  description = "Cloud Run AI Copilot HTTPS URI."
}

output "budget_alert_enabled" {
  value       = module.finops.budget_alert_enabled
  description = "Whether FinOps budget alert is enabled."
}
