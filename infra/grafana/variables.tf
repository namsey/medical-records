variable "alert_email" {
  description = "Where alert emails go. Set it in terraform.tfvars (git-ignored)."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "alert_env" {
  description = "The env label the alerts watch. Only prod alerts; staging is for trying things."
  type        = string
  default     = "prod"
}

# The runbook (docs/MONITORING.md section 16) that each alert links to, with the alert's heading as the anchor.
variable "runbook_base_url" {
  description = "URL of docs/MONITORING.md, where section 16 has one heading per alert."
  type        = string
  default     = "https://github.com/namsey/medical-records/blob/main/docs/MONITORING.md"
}

# Grafana Cloud creates both data sources with the stack; these are their UIDs (Connections -> Data sources).
variable "prometheus_datasource_uid" {
  description = "UID of the stack's Prometheus (Mimir) data source."
  type        = string
  default     = "grafanacloud-prom"
}

variable "loki_datasource_uid" {
  description = "UID of the stack's Loki data source."
  type        = string
  default     = "grafanacloud-logs"
}
