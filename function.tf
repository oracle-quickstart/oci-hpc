resource "local_file" "updateFuncVariables" {
  depends_on = [oci_queue_queue.queue]
  source  = "func.py.tftpl"
  filename = "${path.module}/function/func.py"  
}

resource "oci_functions_application" "fn_application" {
	compartment_id = var.targetCompartment
    display_name = "${local.cluster_name}-app"
    subnet_ids = [local.subnet_id ]
    shape = "GENERIC_ARM"
}

resource "oci_functions_function" "function" {
    application_id = oci_functions_application.fn_application.id
    display_name = "write_node_function"
    image = "yyz.ocir.io/hpc_limited_availability/tough-deer-registry:latest"
    memory_in_mbs = "128"
    timeout_in_seconds = "300" 
    config = { 
      "REGION" : var.region
      "QUEUE_OCID" : local.queue_ocid
      "CLUSTER_NAME" = local.cluster_name
      "CONTROLLER_NAME" = oci_core_instance.controller.display_name
      "PRIVATE_SUBNET" = var.private_subnet
      "ZONE_NAME" = local.zone_name
      shape = "GENERIC_ARM"
    }
}



