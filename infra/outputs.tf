output "public_ip" {
  description = "Reserved: stays the same if the VM is rebuilt"
  value       = oci_core_public_ip.vm.ip_address
}

output "instance_ocid" {
  value = oci_core_instance.vm.id
}

output "bucket_namespace" {
  value = data.oci_objectstorage_namespace.ns.namespace
}

output "ubuntu_image" {
  description = "Image the VM was built from"
  value       = local.ubuntu_image_id
}

output "restic_repository" {
  value = "s3:https://${data.oci_objectstorage_namespace.ns.namespace}.compat.objectstorage.${var.region}.oraclecloud.com/${oci_objectstorage_bucket.backup.name}"
}
