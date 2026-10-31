terraform {
  required_version = ">= 1.7" # mock_provider in tests/

  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "= 4.50.0"
    }
  }

  # Its own root and its own state, so it never shares state with the OCI resources in infra/.
  # State stays on this machine (infra/grafana/terraform.tfstate), never in git.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# Credentials come only from the environment: GRAFANA_URL (https://<stack>.grafana.net) and GRAFANA_AUTH (a
# service account token, MONITORING.md section 7). Nothing secret is in a file here.
provider "grafana" {}
