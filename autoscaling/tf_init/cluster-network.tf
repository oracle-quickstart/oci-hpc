resource "oci_core_cluster_network" "cluster_network" {
  count =  ( ! var.compute_cluster ) && var.cluster_network && var.node_count > 0 ? 1 : 0
  depends_on     = [oci_core_app_catalog_subscription.mp_image_subscription, oci_core_subnet.private-subnet, oci_core_subnet.public-subnet]
  compartment_id = var.targetCompartment
  instance_pools {
    instance_configuration_id = oci_core_instance_configuration.cluster-network-instance_configuration[0].id
    size                      = var.node_count
    display_name              = local.cluster_name
  }
  freeform_tags = {
      "user" = var.tags
      "cluster_name" = local.cluster_name
      "controller_name" = var.controller_name
      "hostname_convention" = var.hostname_convention
  }
  placement_configuration {
    availability_domain = var.ad
    primary_subnet_id   = local.subnet_id
  }
  timeouts {
    create = local.timeout_ip
  }
  display_name = local.cluster_name
}

