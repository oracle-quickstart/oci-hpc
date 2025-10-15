resource "oci_logging_log_group" "log_group" {
  compartment_id = var.targetCompartment
  display_name   = "${local.cluster_name}_log_group"
  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }  
}

resource "oci_logging_log" "node_starting_event_log" {
  display_name = "${local.cluster_name}_node_starting_event_log"
  log_group_id = oci_logging_log_group.log_group.id
  log_type     = "SERVICE"
  configuration {
    source {
      category    = "ruleexecutionlog"
      resource    = oci_events_rule.generated_oci_events_rule.id
      service     = "cloudevents"
      source_type = "OCISERVICE"
    }
    compartment_id = var.targetCompartment
  }
}

resource "oci_logging_log" "node_terminating_event_log" {
  display_name = "${local.cluster_name}_node_terminating_event_log"
  log_group_id = oci_logging_log_group.log_group.id
  log_type     = "SERVICE"
  configuration {
    source {
      category    = "ruleexecutionlog"
      resource    = oci_events_rule.generated_oci_events_rule_2.id
      service     = "cloudevents"
      source_type = "OCISERVICE"
    }
    compartment_id = var.targetCompartment
  }
}



resource "oci_logging_log" "app_invoke_log" {
  display_name = "${local.cluster_name}_app_invoke_log"
  log_group_id = oci_logging_log_group.log_group.id
  log_type     = "SERVICE"
  configuration {
    source {
      category    = "invoke"
      resource    = oci_functions_application.fn_application.id
      service     = "functions"
      source_type = "OCISERVICE"
    }
    compartment_id = var.targetCompartment
  }
}