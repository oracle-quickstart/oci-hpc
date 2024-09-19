resource "oci_core_compute_cluster" "compute_cluster" {
  count = var.compute_cluster && var.cluster_network && var.node_count > 0 ? 1 : 0
    #Required
    availability_domain = var.ad
    compartment_id = var.targetCompartment

    #Optional
    display_name = local.cluster_name
    freeform_tags = {
      "user" = var.tags
      "cluster_name" = local.cluster_name
      "parent_cluster" = local.cluster_name
  }
}