# DEPLOY.md Part A, as code. The compartment (A3) already exists and is only looked up.

data "oci_identity_compartments" "app" {
  compartment_id = var.tenancy_ocid
  name           = var.compartment_name
  state          = "ACTIVE"
}

locals {
  compartment_id = one(data.oci_identity_compartments.app.compartments).id
  name           = "medical-records"
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
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = local.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${local.name}-igw"
  enabled        = true
}

resource "oci_core_default_route_table" "main" {
  manage_default_resource_id = oci_core_vcn.main.default_route_table_id
  display_name               = "${local.name}-routes"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

# Replaces the VCN's default list (which allows 22 from anywhere): 22 from listed IPs only, 80/443 from anywhere, nothing else.
resource "oci_core_default_security_list" "main" {
  manage_default_resource_id = oci_core_vcn.main.default_security_list_id
  display_name               = "${local.name}-security-list"

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

resource "oci_core_subnet" "public" {
  compartment_id    = local.compartment_id
  vcn_id            = oci_core_vcn.main.id
  display_name      = "${local.name}-public-subnet"
  cidr_block        = "10.0.0.0/24"
  dns_label         = "public"
  route_table_id    = oci_core_default_route_table.main.id
  security_list_ids = [oci_core_default_security_list.main.id]
}

# ---------- A6. Compute instance ----------

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
  compartment_id      = local.compartment_id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  fault_domain        = var.fault_domain == "" ? null : var.fault_domain
  display_name        = "${local.name}-vm"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gb
  }

  source_details {
    source_type             = "image"
    source_id               = local.ubuntu_image_id
    boot_volume_size_in_gbs = var.boot_volume_gb
  }

  is_pv_encryption_in_transit_enabled = true

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = false # the reserved IP below is attached instead
    hostname_label   = "app"
  }

  metadata = {
    ssh_authorized_keys = trimspace(file(pathexpand(var.ssh_public_key_path)))
    user_data           = base64encode(file("${path.module}/cloud-init.yaml"))
  }

  lifecycle {
    # A newer Ubuntu image, an edited cloud-init or another fault domain must never rebuild the running VM.
    ignore_changes = [source_details[0].source_id, metadata["user_data"], fault_domain]
  }
}

# Reserved public IP (free; limit 6 per region): survives rebuilding the VM, so the DuckDNS record stays valid.
data "oci_core_vnic_attachments" "vm" {
  compartment_id = local.compartment_id
  instance_id    = oci_core_instance.vm.id
}

data "oci_core_private_ips" "vm" {
  vnic_id = data.oci_core_vnic_attachments.vm.vnic_attachments[0].vnic_id
}

resource "oci_core_public_ip" "vm" {
  compartment_id = local.compartment_id
  display_name   = "${local.name}-ip"
  lifetime       = "RESERVED"
  private_ip_id  = [for ip in data.oci_core_private_ips.vm.private_ips : ip.id if ip.is_primary][0]

  lifecycle {
    prevent_destroy = true
  }
}

# ---------- A8. Block volume for the database and files ----------

resource "oci_core_volume" "data" {
  compartment_id      = local.compartment_id
  availability_domain = oci_core_instance.vm.availability_domain
  display_name        = "${local.name}-data"
  size_in_gbs         = var.data_volume_gb
  vpus_per_gb         = 10 # Balanced

  lifecycle {
    prevent_destroy = true
  }
}

resource "oci_core_volume_attachment" "data" {
  attachment_type                     = "paravirtualized"
  instance_id                         = oci_core_instance.vm.id
  volume_id                           = oci_core_volume.data.id
  device                              = "/dev/oracleoci/oraclevdb"
  is_pv_encryption_in_transit_enabled = true
  is_read_only                        = false
}

# ---------- A9. Backup bucket ----------

resource "oci_objectstorage_bucket" "backup" {
  compartment_id = local.compartment_id
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  name           = "${local.name}-backup"
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = "Enabled"

  lifecycle {
    prevent_destroy = true
  }
}
