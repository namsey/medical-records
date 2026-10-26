# DEPLOY.md Part A, as code. The compartment (A3) already exists and is only looked up.
#
# Two environments, one VM each, from var.environments:
#   prod    1 OCPU, 8 GB RAM, 50 GB boot + 100 GB data volume, FAULT-DOMAIN-1, subnet 10.0.0.0/24, backups
#   staging 1 OCPU, 4 GB RAM, 50 GB boot, no data volume,       FAULT-DOMAIN-2, subnet 10.0.1.0/24, no backups
# Always Free totals: 2 of 2 OCPUs, 12 of 12 GB RAM, 200 of 200 GB boot + block storage (validated in
# variables.tf). Both share one VCN and internet gateway; the backup bucket, IAM and budget belong to prod.

data "oci_identity_compartments" "app" {
  compartment_id = var.tenancy_ocid
  name           = var.compartment_name
  state          = "ACTIVE"
}

locals {
  compartment_id = one(data.oci_identity_compartments.app.compartments).id
  name           = "medical-records"
  tags           = { app = local.name }

  # Only prod gets a data volume by default (data_volume_gb = 0 means none).
  data_volumes = { for env, e in var.environments : env => e if e.data_volume_gb > 0 }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.tenancy_ocid
}

# ---------- A4. Network ----------

resource "oci_core_vcn" "main" {
  compartment_id = local.compartment_id
  display_name   = "${local.name}-vcn"
  cidr_blocks    = ["10.0.0.0/16"]
  dns_label      = "medrec"
  freeform_tags  = merge(local.tags, { env = "shared" })
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = local.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${local.name}-igw"
  enabled        = true
  freeform_tags  = merge(local.tags, { env = "shared" })
}

resource "oci_core_default_route_table" "main" {
  manage_default_resource_id = oci_core_vcn.main.default_route_table_id
  display_name               = "${local.name}-routes"
  freeform_tags              = merge(local.tags, { env = "shared" })

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

# The VCN's default list allows 22 from anywhere. It is emptied here (nothing in, nothing out) and attached to no
# subnet, so a subnet created by hand later is closed until it gets a list of its own.
resource "oci_core_default_security_list" "main" {
  manage_default_resource_id = oci_core_vcn.main.default_security_list_id
  display_name               = "${local.name}-default-security-list-unused"
  freeform_tags              = merge(local.tags, { env = "shared" })
}

# One per environment: 22 from listed IPs only, 80/443 from anywhere, nothing else.
resource "oci_core_security_list" "env" {
  for_each = var.environments

  compartment_id = local.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${local.name}-${each.key}-security-list"
  freeform_tags  = merge(local.tags, { env = each.key })

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  dynamic "ingress_security_rules" {
    for_each = var.ssh_allowed_cidrs
    content {
      description = "SSH from ${ingress_security_rules.key} only"
      source      = ingress_security_rules.value
      protocol    = "6"
      tcp_options {
        min = 22
        max = 22
      }
    }
  }

  ingress_security_rules {
    description = "HTTP (Let's Encrypt and redirect to HTTPS)"
    source      = "0.0.0.0/0"
    protocol    = "6"
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    description = "HTTPS (the app)"
    source      = "0.0.0.0/0"
    protocol    = "6"
    tcp_options {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_subnet" "env" {
  for_each = var.environments

  compartment_id    = local.compartment_id
  vcn_id            = oci_core_vcn.main.id
  display_name      = "${local.name}-${each.key}-subnet"
  cidr_block        = each.value.subnet_cidr
  dns_label         = each.key
  route_table_id    = oci_core_default_route_table.main.id
  security_list_ids = [oci_core_security_list.env[each.key].id]
  freeform_tags     = merge(local.tags, { env = each.key })
}

# ---------- A6. Compute instances ----------

data "oci_core_images" "ubuntu" {
  compartment_id           = local.compartment_id
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
  state                    = "AVAILABLE"
}

locals {
  # Newest aarch64 build; minimal images are skipped.
  ubuntu_image_id = [
    for img in data.oci_core_images.ubuntu.images : img.id
    if strcontains(img.display_name, "aarch64") && !strcontains(img.display_name, "Minimal")
  ][0]
}

resource "oci_core_instance" "vm" {
  for_each = var.environments

  compartment_id      = local.compartment_id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  fault_domain        = each.value.fault_domain
  display_name        = "${local.name}-${each.key}"
  shape               = "VM.Standard.A1.Flex"
  freeform_tags       = merge(local.tags, { env = each.key })

  shape_config {
    ocpus         = each.value.ocpus
    memory_in_gbs = each.value.memory_gb
  }

  source_details {
    source_type             = "image"
    source_id               = local.ubuntu_image_id
    boot_volume_size_in_gbs = each.value.boot_volume_gb
  }

  is_pv_encryption_in_transit_enabled = true

  create_vnic_details {
    subnet_id        = oci_core_subnet.env[each.key].id
    assign_public_ip = false # the reserved IP below is attached instead
    hostname_label   = each.value.hostname
    freeform_tags    = merge(local.tags, { env = each.key })
  }

  metadata = {
    ssh_authorized_keys = trimspace(file(pathexpand(var.ssh_public_key_path)))
    user_data           = base64encode(file("${path.module}/cloud-init.yaml"))
  }

  lifecycle {
    # A newer Ubuntu image, an edited cloud-init or another fault domain must never rebuild a running VM.
    ignore_changes = [source_details[0].source_id, metadata["user_data"], fault_domain]
  }
}

# Reserved public IPs (free; limit 6 per region): survive rebuilding a VM, so its DuckDNS record stays valid.
data "oci_core_vnic_attachments" "vm" {
  for_each = var.environments

  compartment_id = local.compartment_id
  instance_id    = oci_core_instance.vm[each.key].id
}

data "oci_core_private_ips" "vm" {
  for_each = var.environments

  vnic_id = data.oci_core_vnic_attachments.vm[each.key].vnic_attachments[0].vnic_id
}

resource "oci_core_public_ip" "vm" {
  for_each = var.environments

  compartment_id = local.compartment_id
  display_name   = "${local.name}-${each.key}-ip"
  lifetime       = "RESERVED"
  private_ip_id  = [for ip in data.oci_core_private_ips.vm[each.key].private_ips : ip.id if ip.is_primary][0]
  freeform_tags  = merge(local.tags, { env = each.key })

  lifecycle {
    prevent_destroy = true
  }
}

# ---------- A8. Block volume for the database and files (prod only) ----------

resource "oci_core_volume" "data" {
  for_each = local.data_volumes

  compartment_id      = local.compartment_id
  availability_domain = oci_core_instance.vm[each.key].availability_domain
  display_name        = "${local.name}-${each.key}-data"
  size_in_gbs         = each.value.data_volume_gb
  vpus_per_gb         = 10 # Balanced
  freeform_tags       = merge(local.tags, { env = each.key })

  lifecycle {
    prevent_destroy = true
  }
}

resource "oci_core_volume_attachment" "data" {
  for_each = local.data_volumes

  attachment_type                     = "paravirtualized"
  instance_id                         = oci_core_instance.vm[each.key].id
  volume_id                           = oci_core_volume.data[each.key].id
  device                              = "/dev/oracleoci/oraclevdb"
  is_pv_encryption_in_transit_enabled = true
  is_read_only                        = false
}

# ---------- A9. Backup bucket (prod only) ----------

resource "oci_objectstorage_bucket" "backup" {
  compartment_id = local.compartment_id
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "${local.name}-backup"
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = "Enabled"
  freeform_tags  = merge(local.tags, { env = "prod" })

  lifecycle {
    prevent_destroy = true
  }
}
