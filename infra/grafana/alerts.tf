# The alerts of docs/MONITORING.md section 7, on the prod VM's data (env label from Alloy). Each rule is one query (A)
# and one threshold on it (B). "No data" means healthy for all of them: the log counts and unit states return nothing
# when all is well, and "VM silent" uses absent_over_time, which returns 1 only when the metrics stop. That rule is
# the only signal when the whole VM is gone (there is no outside check such as UptimeRobot), so keep it.
locals {
  env  = var.alert_env
  app  = "{env=\"${var.alert_env}\", syslog_identifier=\"medical-records-app\"}"
  unit = "node_systemd_unit_state{env=\"${var.alert_env}\", state=\"failed\", name="
  disk = "env=\"${var.alert_env}\", mountpoint=~\"/|/srv/medical-records\""

  rules = [
    {
      name     = "VM silent"
      source   = "prometheus"
      expr     = "absent_over_time(up{job=\"integrations/node_exporter\", env=\"${local.env}\"}[10m])"
      above    = 0
      for      = "0s"
      severity = "critical"
      summary  = "No metrics from the ${local.env} VM for 10 minutes: the VM is down, or Alloy stopped."
      lookback = 600
    },
    {
      name     = "Disk filling"
      source   = "prometheus"
      expr     = "100 * (1 - node_filesystem_avail_bytes{${local.disk}} / node_filesystem_size_bytes{${local.disk}})"
      above    = 80
      for      = "0s"
      severity = "warning"
      summary  = "A disk on the ${local.env} VM is more than 80% full."
      lookback = 600
    },
    {
      name     = "Memory"
      source   = "prometheus"
      expr     = "100 * (1 - node_memory_MemAvailable_bytes{env=\"${local.env}\"} / node_memory_MemTotal_bytes{env=\"${local.env}\"})"
      above    = 90
      for      = "10m"
      severity = "warning"
      summary  = "Memory on the ${local.env} VM has been more than 90% used for 10 minutes."
      lookback = 600
    },
    {
      name     = "Backup failed"
      source   = "prometheus"
      expr     = "${local.unit}\"medical-records-backup.service\"}"
      above    = 0
      for      = "0s"
      severity = "critical"
      summary  = "The nightly backup on the ${local.env} VM failed."
      lookback = 600
    },
    {
      name     = "Deploy agent failing"
      source   = "prometheus"
      expr     = "${local.unit}\"medical-records-deploy.service\"}"
      above    = 0
      for      = "10m"
      severity = "warning"
      summary  = "The deploy agent on the ${local.env} VM has been failing for 10 minutes."
      lookback = 600
    },
    {
      name     = "App errors"
      source   = "loki"
      expr     = "sum(count_over_time(${local.app} |= \"Unhandled\" [15m]))"
      above    = 0
      for      = "0s"
      severity = "warning"
      summary  = "The app logged an unhandled error on ${local.env} in the last 15 minutes."
      lookback = 900
    },
    {
      name     = "Virus scanner down"
      source   = "loki"
      expr     = "sum(count_over_time(${local.app} |= \"Virus scanner unavailable\" [15m]))"
      above    = 0
      for      = "0s"
      severity = "warning"
      summary  = "The app could not reach ClamAV on ${local.env} in the last 15 minutes."
      lookback = 900
    },
    {
      name     = "Sign-in attempts spike"
      source   = "loki"
      expr     = "sum(count_over_time(${local.app} |= \"Sign-in rejected\" [15m]))"
      above    = 20
      for      = "0s"
      severity = "warning"
      summary  = "More than 20 rejected sign-ins on ${local.env} in 15 minutes."
      lookback = 900
    },
  ]

  datasource_uid = {
    prometheus = data.grafana_data_source.prometheus.uid
    loki       = data.grafana_data_source.loki.uid
  }
}

resource "grafana_rule_group" "prod" {
  name             = "${local.env} alerts"
  folder_uid       = grafana_folder.this.uid
  interval_seconds = 60

  dynamic "rule" {
    for_each = local.rules
    content {
      name           = rule.value.name
      condition      = "B"
      for            = rule.value.for
      no_data_state  = "OK"
      exec_err_state = "Error"
      labels         = { severity = rule.value.severity, env = local.env }
      annotations = {
        summary     = rule.value.summary
        description = "Query: ${rule.value.expr}. What to do: docs/MONITORING.md (mon-6 adds a runbook entry per alert)."
      }

      data {
        ref_id         = "A"
        datasource_uid = local.datasource_uid[rule.value.source]
        relative_time_range {
          from = rule.value.lookback
          to   = 0
        }
        # Instant queries: one value per series at evaluation time, so the threshold needs no reduce step.
        model = jsonencode(rule.value.source == "prometheus" ? {
          refId   = "A"
          expr    = rule.value.expr
          instant = true
          range   = false
          } : {
          refId     = "A"
          expr      = rule.value.expr
          queryType = "instant"
        })
      }

      data {
        ref_id         = "B"
        datasource_uid = "__expr__"
        relative_time_range {
          from = 0
          to   = 0
        }
        model = jsonencode({
          refId      = "B"
          type       = "threshold"
          expression = "A"
          datasource = { type = "__expr__", uid = "__expr__" }
          conditions = [{ evaluator = { type = "gt", params = [rule.value.above] } }]
        })
      }
    }
  }
}
