
resource "oci_identity_auth_token" "auth_token" {
  count       = var.use_OCI_generated_container || var.use_existing_auth_token ? 0 : 1
  provider    = oci.home
  description = "${local.cluster_name}-token"
  user_id     = var.current_user_ocid
}


resource "oci_artifacts_container_repository" "container_repository" {
  count          = var.use_OCI_generated_container || var.use_existing_registry ? 0 : 1
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
  shape          = "GENERIC_X86"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "time_sleep" "wait_for_registry_to_be_ready" {
  count           = var.use_OCI_generated_container || var.use_existing_auth_token ? 0 : 1
  depends_on      = [oci_identity_auth_token.auth_token]
  create_duration = "240s"
}

resource "null_resource" "Login2OCIR" {
  count      = var.use_OCI_generated_container ? 0 : 1
  depends_on = [oci_functions_application.fn_application, oci_artifacts_container_repository.container_repository, oci_identity_auth_token.auth_token, time_sleep.wait_for_registry_to_be_ready]

  provisioner "local-exec" {
    command     = "echo '${local.auth_token}' | docker login -u '${local.ocir_namespace}/${data.oci_identity_user.user.name}' ${local.region_key}.ocir.io --password-stdin"
    working_dir = "${path.module}/function/"
  }
}


resource "null_resource" "function_Push2OCIR" {
  depends_on = [null_resource.Login2OCIR, local_file.updateFuncVariables]
  count      = var.use_OCI_generated_container ? 0 : 1
  provisioner "local-exec" {
    command     = "fn update context oracle.compartment-id ${var.targetCompartment}"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "fn build --verbose"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "image=$(docker images | grep oci-write-controller-queue | awk -F ' ' '{print $3}') ; docker tag $image ${local.region_key}.ocir.io/${local.ocir_namespace}/${data.oci_artifacts_container_repository.container_repo[0].display_name}:latest"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "docker push ${local.region_key}.ocir.io/${local.ocir_namespace}/${data.oci_artifacts_container_repository.container_repo[0].display_name}:latest"
    working_dir = "${path.module}/function/"
  }
}

resource "oci_functions_function" "function" {
  depends_on         = [null_resource.function_Push2OCIR]
  application_id     = oci_functions_application.fn_application.id
  display_name       = "write_node_function"
  image              = local.ocir_image
  memory_in_mbs      = "128"
  timeout_in_seconds = "300"
  config = {
    "REGION" : var.region
    "QUEUE_OCID" : local.queue_ocid
    "CLUSTER_NAME"    = local.cluster_name
    "CONTROLLER_NAME" = "${local.cluster_name}-controller"
    "PRIVATE_SUBNET"  = data.oci_core_subnet.private_subnet.cidr_block
    "ZONE_NAME"       = local.zone_name
    shape             = "GENERIC_X86"
  }

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}



