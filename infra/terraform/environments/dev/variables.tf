variable "project_id" {
  type        = string
  description = "GCP Project ID."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Primary GCP region for GCS, BigQuery, Artifact Registry, and Cloud Run."
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "Deployment environment label."
}

variable "billing_account_id" {
  type        = string
  default     = ""
  description = "Optional GCP Billing Account ID to enable FinOps monthly budget alerts."
}

variable "monthly_budget_usd" {
  type        = number
  default     = 15
  description = "Monthly FinOps budget threshold in USD."
}

variable "deploy_cloud_run" {
  type        = bool
  default     = false
  description = "Enable Cloud Run Service & Job once container image is pushed to Artifact Registry."
}

variable "container_image_tag" {
  type        = string
  default     = "latest"
  description = "Container image tag deployed to Cloud Run."
}
