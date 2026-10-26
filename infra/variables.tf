variable "oci_profile" {
  description = "Profile in ~/.oci/config"
  type        = string
  default     = "DEFAULT"
}

variable "tenancy_ocid" {
  description = "Tenancy OCID (root compartment)"
  type        = string
}

variable "region" {
  description = "Home region: Always Free resources only exist there"
  type        = string
  default     = "ap-mumbai-1"
}

variable "compartment_name" {
  description = "Existing compartment (created in the console) that holds everything"
  type        = string
  default     = "medical-records"
}

variable "ssh_allowed_cidrs" {
  description = "The only sources allowed to reach port 22, each a single IPv4 address, e.g. 203.0.113.7/32"
  type        = map(string) # label => CIDR

  validation {
    condition     = alltrue([for c in values(var.ssh_allowed_cidrs) : can(cidrhost(c, 0)) && endswith(c, "/32")])
    error_message = "Use single IPv4 addresses with /32."
  }
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key put on the VMs"
  type        = string
}

variable "alert_email" {
  description = "Email that receives the budget alert"
  type        = string
}

variable "environments" {
  description = "One VM per environment (DEPLOY.md A6). data_volume_gb = 0 means no data volume. Totals must stay inside Always Free."
  type = map(object({
    ocpus          = number
    memory_gb      = number
    boot_volume_gb = number
    data_volume_gb = number
    fault_domain   = string
    subnet_cidr    = string
    hostname       = string
  }))
  default = {
    prod    = { ocpus = 1, memory_gb = 8, boot_volume_gb = 50, data_volume_gb = 100, fault_domain = "FAULT-DOMAIN-1", subnet_cidr = "10.0.0.0/24", hostname = "prod" }
    staging = { ocpus = 1, memory_gb = 4, boot_volume_gb = 50, data_volume_gb = 0, fault_domain = "FAULT-DOMAIN-2", subnet_cidr = "10.0.1.0/24", hostname = "staging" }
  }

  validation {
    condition     = alltrue([for k in keys(var.environments) : contains(["prod", "staging"], k)])
    error_message = "Only the environments \"prod\" and \"staging\" are allowed."
  }

  validation {
    condition     = try(var.environments["prod"].data_volume_gb, 0) > 0
    error_message = "prod needs a data volume: set environments.prod.data_volume_gb above 0 (the database and files live there)."
  }

  validation {
    condition     = sum(concat([0], [for e in values(var.environments) : e.ocpus])) <= 2
    error_message = "Always Free allows 2 A1 OCPUs in total: the ocpus of all environments add up to more."
  }

  validation {
    condition     = sum(concat([0], [for e in values(var.environments) : e.memory_gb])) <= 12
    error_message = "Always Free allows 12 GB of A1 memory in total: the memory_gb of all environments add up to more."
  }

  validation {
    condition     = sum(concat([0], [for e in values(var.environments) : e.boot_volume_gb + e.data_volume_gb])) <= 200
    error_message = "Always Free allows 200 GB of boot + block volumes in total: boot_volume_gb + data_volume_gb of all environments add up to more."
  }

  validation {
    condition     = alltrue([for e in values(var.environments) : e.boot_volume_gb >= 47])
    error_message = "boot_volume_gb must be at least 47 (the smallest boot volume for the Ubuntu 24.04 image)."
  }

  validation {
    condition     = length(distinct([for e in values(var.environments) : e.fault_domain])) == length(var.environments)
    error_message = "Each environment needs its own fault_domain."
  }

  validation {
    condition     = length(distinct([for e in values(var.environments) : e.subnet_cidr])) == length(var.environments)
    error_message = "Each environment needs its own subnet_cidr."
  }
}

variable "budget_amount" {
  description = "Monthly budget, in the tenancy's billing currency"
  type        = number
  default     = 1
}
