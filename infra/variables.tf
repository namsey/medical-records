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
  description = "Path to the SSH public key put on the VM"
  type        = string
}

variable "alert_email" {
  description = "Email that receives the budget alert"
  type        = string
}

variable "fault_domain" {
  description = "FAULT-DOMAIN-1/2/3, or empty to let Oracle choose (the retry loop sets it per try)"
  type        = string
  default     = ""
}

variable "instance_ocpus" {
  description = "A1 OCPUs (Always Free allows 2 in total)"
  type        = number
  default     = 2
}

variable "instance_memory_gb" {
  description = "A1 memory in GB (Always Free allows 12 in total)"
  type        = number
  default     = 12
}

variable "boot_volume_gb" {
  type    = number
  default = 50
}

variable "data_volume_gb" {
  type    = number
  default = 100
}

variable "budget_amount" {
  description = "Monthly budget, in the tenancy's billing currency"
  type        = number
  default     = 1
}
