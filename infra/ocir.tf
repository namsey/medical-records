# DEPLOY.md A12 (ctr-3): the private container repository the VMs deploy from, and two users limited to it:
#   ci-image-pusher  GitHub Actions: pushes images and moves the "staging" / "prod" tags
#   vm-image-puller  both VMs: pull only
# Auth tokens are NOT made here (they would land in state): create one per user in the console after apply
# (Identity & Security -> Domains -> Default domain -> Users -> <user> -> Auth tokens -> Generate token).

data "oci_identity_regions" "all" {}

locals {
  # OCIR hosts use the region key in lower case, e.g. bom.ocir.io for ap-mumbai-1.
  ocir_registry = "${lower(one([for r in data.oci_identity_regions.all.regions : r.key if r.name == var.region]))}.ocir.io"
}

resource "oci_artifacts_container_repository" "app" {
  compartment_id = local.compartment_id
  display_name   = "${local.name}/app"
  is_public      = false
  is_immutable   = false # the pipeline moves the "staging" and "prod" tags to new images
  freeform_tags  = merge(local.tags, { env = "shared" })

  readme {
    format  = "TEXT_MARKDOWN"
    content = "The medical-records app image (github.com/namsey/medical-records). Tags: `sha-<commit>` per build of main, `vX.Y.Z` per release, and `staging` / `prod`, which the VMs deploy. See DEPLOY.md."
  }
}

resource "oci_identity_group" "image_pushers" {
  compartment_id = var.tenancy_ocid
  name           = "${local.name}-image-pushers"
  description    = "Pushes and retags images in ${oci_artifacts_container_repository.app.display_name} (GitHub Actions)"
  freeform_tags  = merge(local.tags, { env = "shared" })
}

resource "oci_identity_group" "image_pullers" {
  compartment_id = var.tenancy_ocid
  name           = "${local.name}-image-pullers"
  description    = "Pulls images from ${oci_artifacts_container_repository.app.display_name} (the VMs)"
  freeform_tags  = merge(local.tags, { env = "shared" })
}

resource "oci_identity_user" "ci_image_pusher" {
  compartment_id = var.tenancy_ocid
  name           = "ci-image-pusher"
  description    = "medical-records GitHub Actions: pushes the app image and moves its staging/prod tags"
  email          = replace(var.alert_email, "@", "+oci-ci-image-pusher@") # identity domains require an email
  freeform_tags  = merge(local.tags, { env = "shared" })
}

resource "oci_identity_user" "vm_image_puller" {
  compartment_id = var.tenancy_ocid
  name           = "vm-image-puller"
  description    = "medical-records VMs: pull the app image"
  email          = replace(var.alert_email, "@", "+oci-vm-image-puller@")
  freeform_tags  = merge(local.tags, { env = "shared" })
}

resource "oci_identity_user_group_membership" "ci_image_pusher" {
  group_id = oci_identity_group.image_pushers.id
  user_id  = oci_identity_user.ci_image_pusher.id
}

resource "oci_identity_user_group_membership" "vm_image_puller" {
  group_id = oci_identity_group.image_pullers.id
  user_id  = oci_identity_user.vm_image_puller.id
}

# A push (and a retag, which is a push of the same manifest under another tag) needs REPOSITORY_READ and
# REPOSITORY_UPDATE, which only "manage repos" grants ("use repos" was refused: "not authorized"). The pusher gets
# just those two, so it cannot create or delete repositories or images; "read repos" allows pulling only.
resource "oci_identity_policy" "images" {
  compartment_id = local.compartment_id
  name           = "${local.name}-images"
  description    = "Push and pull access to the ${oci_artifacts_container_repository.app.display_name} repository only"
  freeform_tags  = merge(local.tags, { env = "shared" })

  statements = [
    "Allow group ${oci_identity_group.image_pushers.name} to manage repos in compartment ${var.compartment_name} where all { target.repo.name = '${oci_artifacts_container_repository.app.display_name}', any { request.permission = 'REPOSITORY_READ', request.permission = 'REPOSITORY_UPDATE' } }",
    "Allow group ${oci_identity_group.image_pullers.name} to read repos in compartment ${var.compartment_name} where target.repo.name = '${oci_artifacts_container_repository.app.display_name}'",
  ]
}
