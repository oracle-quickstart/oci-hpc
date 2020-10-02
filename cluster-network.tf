resource "oci_core_cluster_network" "cluster_network" {
  count = var.cluster_network ? 1 : 0
  depends_on     = [oci_core_app_catalog_subscription.mp_image_subscription, oci_core_subnet.private-subnet, oci_core_subnet.public-subnet]
  compartment_id = var.targetCompartment
  instance_pools {
    instance_configuration_id = oci_core_instance_configuration.cluster-network-instance_configuration[0].id
    size                      = var.node_count
    display_name              = local.cluster_name
  }
  placement_configuration {
    availability_domain = var.ad
    primary_subnet_id   = local.subnet_id
  }
  timeouts {
    create = "180m"
  }
  display_name = local.cluster_name
}

