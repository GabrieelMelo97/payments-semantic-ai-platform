variable "project_id" {
  type        = string
  description = "GCP Project ID."
}

variable "region" {
  type        = string
  description = "GCP Region."
}

variable "repository_id" {
  type        = string
  description = "Artifact Registry Docker repository ID."
}

variable "container_image" {
  type        = string
  description = "Container image URI for Cloud Run Job and AI Copilot service."
}

variable "dbt_service_account" {
  type        = string
  description = "Service account email for dbt Cloud Run Job."
}

variable "copilot_service_account" {
  type        = string
  description = "Service account email for AI Copilot Cloud Run Service."
}

variable "raw_bucket_name" {
  type        = string
  description = "GCS raw bucket name."
}

variable "gemini_model" {
  type        = string
  default     = "gemini-2.5-flash"
  description = "Vertex AI Gemini model name."
}

variable "deploy_cloud_run" {
  type        = bool
  default     = false
  description = "Set true after pushing container image to Artifact Registry."
}

variable "labels" {
  type        = map(string)
  description = "Mandatory FinOps labels."
}

resource "google_artifact_registry_repository" "platform" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = "Container images for Payments Semantic AI Platform."
  format        = "DOCKER"
  labels        = var.labels
}

resource "google_cloud_run_v2_job" "dbt_build" {
  count               = var.deploy_cloud_run ? 1 : 0
  project             = var.project_id
  name                = "payments-dbt-build"
  location            = var.region
  deletion_protection = false
  labels              = var.labels

  template {
    template {
      service_account = var.dbt_service_account
      timeout         = "600s"

      containers {
        image   = var.container_image
        command = ["dbt", "build", "--project-dir", "dbt_project", "--profiles-dir", "dbt_project", "--target", "bigquery"]

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "GCP_REGION"
          value = var.region
        }
        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service" "ai_copilot" {
  count               = var.deploy_cloud_run ? 1 : 0
  project             = var.project_id
  name                = "payments-semantic-ai-copilot"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = var.labels

  template {
    service_account = var.copilot_service_account

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      env {
        name  = "APP_ENV"
        value = "gcp"
      }
      env {
        name  = "AI_PROVIDER"
        value = "vertex_ai"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "GCS_RAW_BUCKET"
        value = var.raw_bucket_name
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }
}

output "artifact_registry_url" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.platform.repository_id}"
  description = "Artifact Registry Docker repository URL."
}

output "copilot_service_uri" {
  value       = var.deploy_cloud_run ? google_cloud_run_v2_service.ai_copilot[0].uri : "not-deployed-yet"
  description = "Cloud Run AI Copilot HTTPS URI."
}

resource "google_cloud_run_v2_service" "streamlit_ui" {
  count               = var.deploy_cloud_run ? 1 : 0
  project             = var.project_id
  name                = "payments-semantic-streamlit-ui"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = var.labels

  template {
    service_account = var.copilot_service_account

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.container_image
      command = [
        "streamlit",
        "run",
        "src/payments_platform/app/streamlit_app.py",
        "--server.port=8080",
        "--server.address=0.0.0.0",
        "--server.headless=true",
      ]

      ports {
        container_port = 8080
      }

      env {
        name  = "APP_ENV"
        value = "gcp"
      }
      env {
        name  = "AI_PROVIDER"
        value = "vertex_ai"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "GCS_RAW_BUCKET"
        value = var.raw_bucket_name
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }
}

output "streamlit_ui_uri" {
  value       = var.deploy_cloud_run ? google_cloud_run_v2_service.streamlit_ui[0].uri : "not-deployed-yet"
  description = "Cloud Run Streamlit Executive BI & AI Copilot HTTPS URI."
}
