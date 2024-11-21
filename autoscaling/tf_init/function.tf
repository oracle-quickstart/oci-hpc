resource "local_file" "updateFuncVariables" {
  content  = templatefile("func.py.tftpl", {queue_ocid = local.queue_ocid, cluster_name = local.cluster_name})
  filename = "${path.module}/function/func.py"  
}

resource "oci_identity_auth_token" "auth_token" {
    count          = !var.use_existing_auth_token ? 1 : 0
    description = "${local.cluster_name}-token"
    user_id = var.current_user_ocid
}


resource "oci_artifacts_container_repository" "container_repository" {
    count          = !var.use_existing_registry ? 1 : 0
    compartment_id = var.targetCompartment
    display_name = "${local.cluster_name}-registry"

}


resource "oci_functions_application" "fn_application" {
	compartment_id = var.targetCompartment
    display_name = "${local.cluster_name}-app"
    subnet_ids = [local.subnet_id ]
    shape = "GENERIC_ARM"
}

resource "null_resource" "Login2OCIR" {
  depends_on = [oci_functions_application.fn_application, local.registry_id, local.auth_token]

  provisioner "local-exec" {
    command     = "echo '${local.auth_token}' | docker login -u '${local.ocir_namespace}/${data.oci_identity_user.user.name}' ${local.region_key}.ocir.io --password-stdin"
    working_dir = "${path.module}/function/"
  } 
}


resource "null_resource" "function_Push2OCIR" {
  depends_on = [null_resource.Login2OCIR]

  provisioner "local-exec" {
    command     = "fn update context oracle.compartment-id ${var.targetCompartment}"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "fn build --verbose"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "image=$(docker images | grep oci-write-controller-queue | awk -F ' ' '{print $3}') ; docker tag $image ${local.region_key}.ocir.io/${local.ocir_namespace}/${data.oci_artifacts_container_repository.container_repo.display_name}:latest"
    working_dir = "${path.module}/function/"
  }

  provisioner "local-exec" {
    command     = "docker push ${local.region_key}.ocir.io/${local.ocir_namespace}/${data.oci_artifacts_container_repository.container_repo.display_name}:latest"
    working_dir = "${path.module}/function/"
  }  
}

resource "oci_functions_function" "function" {
	depends_on = [null_resource.function_Push2OCIR]
    application_id = oci_functions_application.fn_application.id
    display_name = "write_node_function"
    image = "${local.region_key}.ocir.io/${local.ocir_namespace}/${data.oci_artifacts_container_repository.container_repo.display_name}:latest"
    memory_in_mbs = "256" 
    config = { 
      "REGION" : "${var.region}"
    shape = "GENERIC_ARM"
    }
}



