# DEPLOY.md A9: backup users, groups and policy. Customer secret keys are NOT made here
# (they would land in state); create them in the console after apply.

resource "oci_identity_group" "backup_writers" {
  compartment_id = var.tenancy_ocid
  name           = "${local.name}-backup-writers"
  description    = "Writes restic backups to ${oci_objectstorage_bucket.backup.name} (the VM)"
  freeform_tags  = merge(local.tags, { env = "prod" })
}

resource "oci_identity_group" "backup_readers" {
  compartment_id = var.tenancy_ocid
  name           = "${local.name}-backup-readers"
  description    = "Reads restic backups from ${oci_objectstorage_bucket.backup.name} (home copy)"
  freeform_tags  = merge(local.tags, { env = "prod" })
}

resource "oci_identity_user" "backup_writer" {
  compartment_id = var.tenancy_ocid
  name           = "backup-writer"
  description    = "medical-records VM: restic backups"
  email          = replace(var.alert_email, "@", "+oci-backup-writer@") # identity domains require an email
  freeform_tags  = merge(local.tags, { env = "prod" })
}

resource "oci_identity_user" "backup_reader" {
  compartment_id = var.tenancy_ocid
  name           = "backup-reader"
  description    = "medical-records home machine: weekly backup copy"
  email          = replace(var.alert_email, "@", "+oci-backup-reader@")
  freeform_tags  = merge(local.tags, { env = "prod" })
}

resource "oci_identity_user_group_membership" "writer" {
  group_id = oci_identity_group.backup_writers.id
  user_id  = oci_identity_user.backup_writer.id
}

resource "oci_identity_user_group_membership" "reader" {
  group_id = oci_identity_group.backup_readers.id
  user_id  = oci_identity_user.backup_reader.id
}

resource "oci_identity_policy" "backup" {
  compartment_id = local.compartment_id
  name           = "${local.name}-backup"
  description    = "Backup access to ${oci_objectstorage_bucket.backup.name} only"
  freeform_tags  = merge(local.tags, { env = "prod" })

  statements = [
    "Allow group ${oci_identity_group.backup_writers.name} to read buckets in compartment ${var.compartment_name} where target.bucket.name = '${oci_objectstorage_bucket.backup.name}'",
    "Allow group ${oci_identity_group.backup_writers.name} to manage objects in compartment ${var.compartment_name} where target.bucket.name = '${oci_objectstorage_bucket.backup.name}'",
    "Allow group ${oci_identity_group.backup_readers.name} to read buckets in compartment ${var.compartment_name} where target.bucket.name = '${oci_objectstorage_bucket.backup.name}'",
    "Allow group ${oci_identity_group.backup_readers.name} to read objects in compartment ${var.compartment_name} where target.bucket.name = '${oci_objectstorage_bucket.backup.name}'",
  ]
}
