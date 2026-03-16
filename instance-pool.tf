resource "oci_core_instance_pool" "instance_pool" {
  count                     = (!var.rdma_enabled) && (!var.stand_alone) && (var.node_count > 0) ? 1 : 0
  depends_on                = [oci_core_app_catalog_subscription.mp_image_subscription, oci_core_subnet.private-subnet, oci_core_subnet.public-subnet, oci_functions_function.function, null_resource.controller]
  compartment_id            = var.targetCompartment
  instance_configuration_id = oci_core_instance_configuration.instance_pool_configuration[0].id
  size                      = var.node_count
  display_name              = local.cluster_name
  freeform_tags = {
    "cluster_name"        = local.cluster_name
    "controller_name"     = oci_core_instance.controller.display_name
    "hostname_convention" = var.hostname_convention
  }
  placement_configurations {
    availability_domain = var.ad
    primary_subnet_id   = local.subnet_id
  }

  timeouts {
    create = local.timeout_ip
  }
}

