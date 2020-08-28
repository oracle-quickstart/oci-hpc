resource "oci_core_instance_pool" "instance_pool" {
  count = var.cluster_network ? 0 : 1
  depends_on     = [oci_core_app_catalog_subscription.mp_image_subscription, oci_core_subnet.private-subnet, oci_core_subnet.public-subnet]
  compartment_id = var.targetCompartment
  instance_configuration_id = oci_core_instance_configuration.instance_pool_configuration[0].id
  size                      = var.node_count
  display_name              = local.cluster_name
  
  placement_configurations {
    availability_domain = var.ad
    primary_subnet_id   = local.subnet_id
  }

  timeouts {
    create = "120m"
  }
}

