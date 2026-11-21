variable "project_id" {
  type        = string
  description = "GCP Project ID."
}

variable "location" {
  type        = string
  description = "BigQuery dataset location."
}

variable "labels" {
  type        = map(string)
  description = "Mandatory FinOps labels."
}

variable "delete_contents_on_destroy" {
  type        = bool
  default     = true
  description = "Allow clean teardown in dev environments."
}

locals {
  datasets = {
    raw       = { id = "payments_raw", desc = "Contract-validated raw payment tables and quarantine." }
    stg       = { id = "payments_stg", desc = "Staging views (1:1 cleaned and deduplicated)." }
    int       = { id = "payments_int", desc = "Intermediate transformation layer." }
    marts     = { id = "payments_marts", desc = "Kimball Star Schema marts & Semantic Layer source of truth." }
    snapshots = { id = "payments_snapshots", desc = "dbt SCD Type 2 snapshots (merchant MDR rates)." }
  }
}

resource "google_bigquery_dataset" "layers" {
  for_each = local.datasets

  project                    = var.project_id
  dataset_id                 = each.value.id
  friendly_name              = each.value.id
  description                = each.value.desc
  location                   = var.location
  delete_contents_on_destroy = var.delete_contents_on_destroy
  labels                     = merge(var.labels, { layer = each.key })
}

output "dataset_ids" {
  value       = { for k, v in google_bigquery_dataset.layers : k => v.dataset_id }
  description = "Map of Medallion/Kimball BigQuery dataset IDs."
}
