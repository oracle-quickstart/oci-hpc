resource "oci_queue_queue" "queue" {
  display_name   = "${local.cluster_name}-queue"
  compartment_id = var.targetCompartment
}