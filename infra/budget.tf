# DEPLOY.md A2. The amount is in the tenancy's billing currency (set by Oracle at sign-up).

resource "oci_budget_budget" "main" {
  compartment_id = var.tenancy_ocid
  display_name   = "${local.name}-budget"
  description    = "Alerts on any spend in the ${var.compartment_name} compartment"
  amount         = var.budget_amount
  reset_period   = "MONTHLY"
  target_type    = "COMPARTMENT"
  targets        = [local.compartment_id]
  freeform_tags  = merge(local.tags, { env = "prod" })
}

resource "oci_budget_alert_rule" "actual_spend" {
  budget_id      = oci_budget_budget.main.id
  display_name   = "any-actual-spend"
  type           = "ACTUAL"
  threshold      = 1
  threshold_type = "PERCENTAGE"
  recipients     = var.alert_email
  message        = "Oracle Cloud: the medical-records compartment is costing money. Check Billing > Cost analysis."
  freeform_tags  = merge(local.tags, { env = "prod" })
}
