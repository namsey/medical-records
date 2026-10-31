# Everything this root makes lives in one folder, so it is easy to tell apart from what Grafana Cloud's integrations
# install.
resource "grafana_folder" "this" {
  title = "HealthKitab"
}

# Looked up rather than trusted: a wrong UID fails at plan, not silently at the first evaluation.
data "grafana_data_source" "prometheus" {
  uid = var.prometheus_datasource_uid
}

data "grafana_data_source" "loki" {
  uid = var.loki_datasource_uid
}

resource "grafana_contact_point" "email" {
  name = "HealthKitab email"

  email {
    addresses    = [var.alert_email]
    single_email = true
  }
}

# This is the stack's whole notification policy tree: applying it replaces any policy made by hand in the UI.
# One route for everything: every alert in the stack goes to the email above.
resource "grafana_notification_policy" "this" {
  contact_point   = grafana_contact_point.email.name
  group_by        = ["grafana_folder", "alertname"]
  group_wait      = "30s"
  group_interval  = "5m"
  repeat_interval = "4h"
}

resource "grafana_dashboard" "app" {
  folder = grafana_folder.this.uid
  config_json = templatefile("${path.module}/dashboards/healthkitab.json.tftpl", {
    prometheus_uid = data.grafana_data_source.prometheus.uid
    loki_uid       = data.grafana_data_source.loki.uid
  })
}
