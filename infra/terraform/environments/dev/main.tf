locals {
  project_name = "payments-semantic-ai-platform"
  common_labels = {
    project    = local.project_name
    env        = var.environment
    managed_by = "terraform"
    domain     = "fintech-payments"
  }
  raw_bucket_name = "${var.project_id}-payments-raw-${var.environment}"
  ar_repo_id      = "payments-semantic-platform"
  container_image = "${var.region}-docker.pkg.dev/${var.project_id}/${local.ar_repo_id}/app:${var.container_image_tag}"
}

module "storage" {
  source      = "../../modules/storage"
  project_id  = var.project_id
  region      = var.region
  bucket_name = local.raw_bucket_name
  labels      = local.common_labels
}

module "warehouse" {
  source     = "../../modules/warehouse"
  project_id = var.project_id
  location   = var.region
  labels     = local.common_labels
}

module "security" {
  source          = "../../modules/security"
  project_id      = var.project_id
  raw_bucket_name = module.storage.bucket_name
  dataset_ids     = module.warehouse.dataset_ids
}

module "compute" {
  source                  = "../../modules/compute"
  project_id              = var.project_id
  region                  = var.region
  repository_id           = local.ar_repo_id
  container_image         = local.container_image
  dbt_service_account     = module.security.service_accounts["dbt_runner"]
  copilot_service_account = module.security.service_accounts["ai_copilot"]
  raw_bucket_name         = module.storage.bucket_name
  deploy_cloud_run        = var.deploy_cloud_run
  labels                  = local.common_labels
}

module "finops" {
  source             = "../../modules/finops"
  project_id         = var.project_id
  billing_account_id = var.billing_account_id
  monthly_budget_usd = var.monthly_budget_usd
}
