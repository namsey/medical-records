# Maps keyed by environment (prod, staging).

output "public_ip" {
  description = "Reserved: stays the same if a VM is rebuilt"
  value       = { for env, ip in oci_core_public_ip.vm : env => ip.ip_address }
}

output "instance_ocid" {
  value = { for env, vm in oci_core_instance.vm : env => vm.id }
}

output "private_ip" {
  value = { for env, vm in oci_core_instance.vm : env => vm.private_ip }
}

output "ssh_command" {
  description = "DEPLOY.md A7"
  value       = { for env, ip in oci_core_public_ip.vm : env => "ssh -i ${trimsuffix(var.ssh_public_key_path, ".pub")} ubuntu@${ip.ip_address}" }
}

output "bucket_namespace" {
  value = data.oci_objectstorage_namespace.ns.namespace
}

output "ubuntu_image" {
  description = "Image the VMs were built from"
  value       = local.ubuntu_image_id
}

output "restic_repository" {
  value = "s3:https://${data.oci_objectstorage_namespace.ns.namespace}.compat.objectstorage.${var.region}.oraclecloud.com/${oci_objectstorage_bucket.backup.name}"
}
