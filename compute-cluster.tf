resource "oci_core_compute_cluster" "compute_cluster" {
  count = (var.stand_alone && var.rdma_enabled && var.node_count > 0) || (var.cluster_network_shape == "BM.GPU.GB200.4" || var.cluster_network_shape == "BM.GPU.GB200-v2.4" || var.cluster_network_shape == "BM.GPU.GB200-v3.4" || var.cluster_network_shape == "BM.GPU.GB300.4") ? 1 : 0
  #Required
  availability_domain = var.ad
  compartment_id      = var.targetCompartment

  #Optional
  display_name = local.cluster_name
  freeform_tags = {
    "cluster_name"        = local.cluster_name
    "controller_name"     = oci_core_instance.controller.display_name
    "hostname_convention" = var.hostname_convention
  }
}