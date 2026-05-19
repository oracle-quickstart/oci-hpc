
resource "oci_identity_auth_token" "auth_token" {
  count = var.use_existing_auth_token ? 0 : (
    var.is_gov_cloud
    ? 1                                  # Gov/air-gapped: need token to mirror
    : (!var.use_OCI_generated_container ? 1 : 0)  # Commercial rebuilds need token; public pull does not
  )
  provider    = oci.home
  description = "${local.cluster_name}-token"
  user_id     = var.current_user_ocid
}


resource "oci_artifacts_container_repository" "container_repository" {
  # In GovCloud always create; elsewhere follow existing logic
  count          = (var.use_OCI_generated_container && var.is_gov_cloud) ? 1 : (var.use_OCI_generated_container || var.use_existing_registry ? 0 : 1)
  compartment_id = var.targetCompartment
  display_name   = "${local.cluster_name}-registry"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}


resource "oci_functions_application" "fn_application" {
  compartment_id = var.targetCompartment
  display_name   = "${local.cluster_name}-app"
  subnet_ids     = [local.subnet_id]
  shape          = local.function_shape
  config = {
    "REGION" : var.region
    "QUEUE_OCID" : local.queue_ocid
    "CLUSTER_NAME"    = local.cluster_name
    "CONTROLLER_NAME" = "${local.cluster_name}-controller"
    "ZONE_NAME"       = local.zone_name
    "VCN_COMPARTMENT" = var.vcn_compartment
    shape             = local.function_shape
  }
  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "time_sleep" "wait_for_registry_to_be_ready" {
  count           = var.use_existing_auth_token ? 0 : (var.is_gov_cloud || !var.use_OCI_generated_container ? 1 : 0)
  depends_on      = [oci_identity_auth_token.auth_token]
  create_duration = "240s"
}

resource "null_resource" "Login2OCIR" {
  # Login whenever we're in GovCloud or when we build/push our own image
  count      = (var.is_gov_cloud || !var.use_OCI_generated_container) ? 1 : 0
  depends_on = [oci_functions_application.fn_application, oci_artifacts_container_repository.container_repository, oci_identity_auth_token.auth_token, time_sleep.wait_for_registry_to_be_ready]

  provisioner "local-exec" {
    command = "echo '${local.auth_token}' | podman login -u '${local.ocir_login_user}' ${local.ocir_host} --password-stdin"
    working_dir = "${path.module}/function/"
  }
}


resource "null_resource" "copy_push2OCIR" {
  count      = var.is_gov_cloud ? 1 : 0
  depends_on = [null_resource.Login2OCIR, oci_artifacts_container_repository.container_repository]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    working_dir = "${path.module}/function/"
    command     = <<-EOT
      set -euo pipefail
      target_repo="${local.ocir_host}"
      namespace="${local.ocir_namespace}"
      repository_name="${data.oci_artifacts_container_repository.container_repo[0].display_name}"
      version="${var.container_version}"
      img_target_latest="$${target_repo}/$${namespace}/$${repository_name}:$${version}"
      img_target_arm64="$${target_repo}/$${namespace}/$${repository_name}:arm64_$${version}"
      img_target_amd64="$${target_repo}/$${namespace}/$${repository_name}:amd64_$${version}"

      # Pull public images from IAD using configured namespace/name
      podman system prune --all --force && podman rmi --all
      podman pull iad.ocir.io/${var.OCI_generated_container_namespace}/${var.OCI_generated_container_name}:arm64_$${version}
      podman pull iad.ocir.io/${var.OCI_generated_container_namespace}/${var.OCI_generated_container_name}:amd64_$${version}

      # Tag and push per-arch images to local registry
      podman tag iad.ocir.io/${var.OCI_generated_container_namespace}/${var.OCI_generated_container_name}:arm64_$${version} "$${img_target_arm64}"
      podman tag iad.ocir.io/${var.OCI_generated_container_namespace}/${var.OCI_generated_container_name}:amd64_$${version} "$${img_target_amd64}"
      podman push "$${img_target_arm64}"
      podman push "$${img_target_amd64}"

      # Build and push multi-arch manifest
      podman image rm -f "$${img_target_latest}" || true
      podman manifest rm "$${img_target_latest}" || true
      podman manifest create "$${img_target_latest}"
      podman manifest add "$${img_target_latest}" "$${img_target_arm64}"
      podman manifest add "$${img_target_latest}" "$${img_target_amd64}"
      podman manifest push "$${img_target_latest}" "$${img_target_latest}"
    EOT
  }
}

resource "null_resource" "function_Push2OCIR" {
  depends_on = [null_resource.Login2OCIR]
  count      = var.use_OCI_generated_container || var.is_gov_cloud ? 0 : 1
  provisioner "local-exec" {
    command     = "fn update context oracle.compartment-id ${var.targetCompartment}"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "fn build --verbose"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "image=$(podman images | grep oci-write-controller-queue | awk -F ' ' '{print $3}') ; podman tag $image ${local.ocir_host}/${local.ocir_namespace}/${data.oci_artifacts_container_repository.container_repo[0].display_name}:${var.container_version}"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "podman push ${local.ocir_host}/${local.ocir_namespace}/${data.oci_artifacts_container_repository.container_repo[0].display_name}:${var.container_version}"
    working_dir = "${path.module}/function/"
  }
}

resource "oci_functions_function" "function" {
  # Depend on both; only one will have instances based on counts, keeping depends_on static
  depends_on         = [null_resource.copy_push2OCIR, null_resource.function_Push2OCIR]
  application_id     = oci_functions_application.fn_application.id
  display_name       = "write_node_function"
  image              = local.ocir_image
  memory_in_mbs      = "128"
  timeout_in_seconds = "300"
  provisioned_concurrency_config {
    strategy = "CONSTANT"
    count    = 40
  }   


  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}
