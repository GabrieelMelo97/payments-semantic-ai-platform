variable "project_id" {
  type        = string
  description = "GCP Project ID."
}

variable "billing_account_id" {
  type        = string
  default     = ""
  description = "Optional GCP Billing Account ID to create a FinOps budget alert."
}

variable "monthly_budget_usd" {
  type        = number
  default     = 15
  description = "Monthly budget threshold in USD for dev environment."
}

data "google_project" "current" {
  count      = var.billing_account_id != "" ? 1 : 0
  project_id = var.project_id
}

resource "google_billing_budget" "monthly_guardrail" {
  count           = var.billing_account_id != "" ? 1 : 0
  billing_account = var.billing_account_id
  display_name    = "payments-semantic-ai-platform-monthly-budget"

  budget_filter {
    projects = ["projects/${data.google_project.current[0].number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.8
  }
  threshold_rules {
    threshold_percent = 1.0
  }
}

output "budget_alert_enabled" {
  value       = var.billing_account_id != ""
  description = "Whether the FinOps billing budget alert resource is active."
}
