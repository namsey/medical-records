terraform {
  required_version = ">= 1.6"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.10.0"
    }
  }

  # State stays on this machine (infra/terraform.tfstate), never in git.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# Credentials come from ~/.oci/config (the API key never enters Terraform).
provider "oci" {
  config_file_profile = var.oci_profile
  region              = var.region
}
