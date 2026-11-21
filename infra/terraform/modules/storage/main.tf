variable "project_id" {
  type        = string
  description = "GCP Project ID."
}

variable "region" {
  type        = string
  description = "GCP Region for the GCS bucket."
}

variable "bucket_name" {
  type        = string
  description = "Globally unique GCS bucket name for validated raw payment files."
}

variable "labels" {
  type        = map(string)
  description = "Mandatory FinOps labels."
}

variable "force_destroy" {
  type        = bool
  default     = true
  description = "Allow clean terraform destroy in non-prod environments."
}

resource "google_storage_bucket" "raw_payments" {
  name                        = var.bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy
  labels                      = var.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 60
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 180
    }
    action {
      type = "Delete"
    }
  }
}

output "bucket_name" {
  value       = google_storage_bucket.raw_payments.name
  description = "Created GCS raw bucket name."
}

output "bucket_url" {
  value       = google_storage_bucket.raw_payments.url
  description = "GCS bucket gs:// URL."
}
