

resource "oci_events_rule" "generated_oci_events_rule" {
  depends_on = [oci_functions_function.function]
  actions {
    actions {
      action_type = "FAAS"
      function_id = oci_functions_function.function.id
      is_enabled  = "true"
    }
  }
  compartment_id = var.targetCompartment
  condition      = "{\"eventType\":[\"com.oraclecloud.computeapi.launchinstance.end\"],\"data\":{\"compartmentId\":[\"${var.targetCompartment}\"]}}"
  description    = "write_node_starting_event"
  display_name   = "${local.cluster_name}_write_node_starting_event"
  is_enabled     = "true"
  
  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}



resource "oci_events_rule" "generated_oci_events_rule_2" {
  depends_on = [oci_functions_function.function]
  actions {
    actions {
      action_type = "FAAS"
      function_id = oci_functions_function.function.id
      is_enabled  = "true"
    }
  }
  compartment_id = var.targetCompartment
  condition      = "{\"eventType\":[\"com.oraclecloud.computeapi.terminateinstance.begin\"],\"data\":{\"compartmentId\":[\"${var.targetCompartment}\"]}}"
  description    = "write_node_terminating_event"
  display_name   = "${local.cluster_name}_write_node_terminating_event"
  is_enabled     = "true"
  
  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}


