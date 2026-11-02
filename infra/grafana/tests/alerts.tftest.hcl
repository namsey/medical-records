# terraform test, with a mock provider: no Grafana stack or token needed (CI runs it).

mock_provider "grafana" {
  mock_data "grafana_data_source" {
    defaults = {
      uid = "mock-uid"
    }
  }
  mock_resource "grafana_folder" {
    defaults = {
      uid = "mock-folder"
    }
  }
}

variables {
  alert_email = "alerts@example.com"
}

run "alerts_match_monitoring_section_7" {
  command = plan

  assert {
    condition = toset([for r in grafana_rule_group.prod.rule : r.name]) == toset([
      "VM silent", "Disk filling", "Memory", "Backup failed", "Deploy agent failing",
      "App errors", "Virus scanner down", "Sign-in attempts spike",
    ])
    error_message = "The rule group must hold exactly the alerts of docs/MONITORING.md section 7."
  }

  assert {
    condition     = alltrue([for r in grafana_rule_group.prod.rule : strcontains(jsondecode(r.data[0].model).expr, "env=\"prod\"")])
    error_message = "Every alert query must be limited to env=\"prod\"."
  }

  assert {
    condition = alltrue([
      for r in grafana_rule_group.prod.rule : jsondecode(r.data[0].model).instant == true && jsondecode(r.data[0].model).range == false
      if can(jsondecode(r.data[0].model).instant)
    ]) && length([for r in grafana_rule_group.prod.rule : r if can(jsondecode(r.data[0].model).instant)]) == 5
    error_message = "The 5 Prometheus queries must send instant/range as JSON booleans, not strings."
  }

  assert {
    condition     = alltrue([for r in grafana_rule_group.prod.rule : r.no_data_state == "OK" && r.condition == "B"])
    error_message = "No data must mean healthy, and B (the threshold) must be the condition."
  }

  assert {
    condition = {
      for r in grafana_rule_group.prod.rule : r.name => jsondecode(r.data[1].model).conditions[0].evaluator.params[0]
      } == {
      "VM silent"  = 0, "Disk filling" = 80, "Memory" = 90, "Backup failed" = 0, "Deploy agent failing" = 0,
      "App errors" = 0, "Virus scanner down" = 0, "Sign-in attempts spike" = 20,
    }
    error_message = "Thresholds must match docs/MONITORING.md section 7."
  }

  assert {
    condition = {
      for r in grafana_rule_group.prod.rule : r.name => r.for if r.for != "0s"
    } == { "Memory" = "10m", "Deploy agent failing" = "10m" }
    error_message = "Only Memory and Deploy agent failing wait 10 minutes before firing."
  }

  assert {
    condition     = strcontains(one([for r in grafana_rule_group.prod.rule : jsondecode(r.data[0].model).expr if r.name == "VM silent"]), "absent_over_time(up{job=\"integrations/node_exporter\"")
    error_message = "VM silent must fire on missing node_exporter metrics."
  }

  assert {
    condition     = nonsensitive(tolist(one(grafana_contact_point.email.email).addresses)) == tolist(["alerts@example.com"])
    error_message = "Alerts must go to alert_email."
  }

  assert {
    condition     = grafana_notification_policy.this.contact_point == grafana_contact_point.email.name
    error_message = "The notification policy must route to the email contact point."
  }
}

run "dashboard_is_valid_json_with_the_data_sources" {
  command = plan

  assert {
    condition     = jsondecode(grafana_dashboard.app.config_json).uid == "healthkitab-app"
    error_message = "The dashboard must render to JSON with a fixed uid."
  }

  assert {
    condition = alltrue([
      for p in jsondecode(grafana_dashboard.app.config_json).panels :
      contains([var.prometheus_datasource_uid, var.loki_datasource_uid], p.datasource.uid) if p.type != "row"
    ])
    error_message = "Every panel must use one of the stack's data sources."
  }
}

run "rejects_a_bad_email" {
  command = plan

  variables {
    alert_email = "not-an-email"
  }

  expect_failures = [var.alert_email]
}
