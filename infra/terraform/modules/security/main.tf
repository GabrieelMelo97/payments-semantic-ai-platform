variable "project_id" {
  type        = string
  description = "GCP Project ID."
}

variable "raw_bucket_name" {
  type        = string
  description = "GCS raw bucket name for scoped ingestion IAM."
}

variable "dataset_ids" {
  type        = map(string)
  description = "Map of BigQuery dataset IDs (raw, stg, int, marts, snapshots)."
}

resource "google_service_account" "ingest" {
  project      = var.project_id
  account_id   = "sa-payments-ingest"
  display_name = "Payments Raw Ingestion Service Account (Least Privilege)"
}

resource "google_service_account" "dbt_runner" {
  project      = var.project_id
  account_id   = "sa-payments-dbt-runner"
  display_name = "Payments dbt Cloud Run Job Service Account (Least Privilege)"
}

resource "google_service_account" "ai_copilot" {
  project      = var.project_id
  account_id   = "sa-payments-ai-copilot"
  display_name = "Payments Governed AI Copilot Service Account (Read-Only Marts + Vertex AI)"
}

# 1. Ingestion SA: write to GCS raw bucket & BigQuery raw dataset only
resource "google_storage_bucket_iam_member" "ingest_bucket_admin" {
  bucket = var.raw_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ingest.email}"
}

resource "google_bigquery_dataset_iam_member" "ingest_raw_editor" {
  project    = var.project_id
  dataset_id = var.dataset_ids["raw"]
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.ingest.email}"
}

resource "google_project_iam_member" "ingest_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.ingest.email}"
}

# 2. dbt Runner SA: read raw, write stg/int/marts/snapshots
resource "google_bigquery_dataset_iam_member" "dbt_raw_viewer" {
  project    = var.project_id
  dataset_id = var.dataset_ids["raw"]
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.dbt_runner.email}"
}

resource "google_bigquery_dataset_iam_member" "dbt_transform_editors" {
  for_each = toset(["stg", "int", "marts", "snapshots"])

  project    = var.project_id
  dataset_id = var.dataset_ids[each.key]
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.dbt_runner.email}"
}

resource "google_project_iam_member" "dbt_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dbt_runner.email}"
}

# 3. AI Copilot SA: read-only ONLY on marts + BigQuery Job User + Vertex AI User
resource "google_bigquery_dataset_iam_member" "copilot_marts_viewer" {
  project    = var.project_id
  dataset_id = var.dataset_ids["marts"]
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.ai_copilot.email}"
}

resource "google_project_iam_member" "copilot_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.ai_copilot.email}"
}

resource "google_project_iam_member" "copilot_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.ai_copilot.email}"
}

output "service_accounts" {
  value = {
    ingest     = google_service_account.ingest.email
    dbt_runner = google_service_account.dbt_runner.email
    ai_copilot = google_service_account.ai_copilot.email
  }
  description = "Least-privilege Service Account emails."
}
