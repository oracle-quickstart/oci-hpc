resource "oci_core_cluster_network" "cluster_network" {
  count          = (!var.stand_alone) && var.rdma_enabled && var.node_count > 0 && (var.cluster_network_shape != "BM.GPU.GB200.4" && var.cluster_network_shape != "BM.GPU.GB200-v2.4" && var.cluster_network_shape != "BM.GPU.GB200-v3.4" && var.cluster_network_shape != "BM.GPU.GB300.4") ? 1 : 0
  depends_on     = [oci_core_app_catalog_subscription.mp_image_subscription, oci_core_subnet.private-subnet, oci_core_subnet.public-subnet, oci_functions_function.function, null_resource.cluster]
  compartment_id = var.targetCompartment
  instance_pools {
    instance_configuration_id = oci_core_instance_configuration.cluster-network-instance_configuration[0].id
    size                      = var.node_count
    display_name              = local.cluster_name
  }
  freeform_tags = {
    "cluster_name"        = local.cluster_name
    "controller_name"     = oci_core_instance.controller.display_name
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


resource "oci_core_compute_gpu_memory_cluster" "compute_gpu_memory_cluster" {
  count                     = var.node_count > 0 && (var.cluster_network_shape == "BM.GPU.GB200.4" || var.cluster_network_shape == "BM.GPU.GB200-v2.4" || var.cluster_network_shape == "BM.GPU.GB200-v3.4" || var.cluster_network_shape == "BM.GPU.GB300.4") ? 1 : 0
  availability_domain       = var.ad
  compartment_id            = var.targetCompartment
  compute_cluster_id        = oci_core_compute_cluster.compute_cluster[0].id
  instance_configuration_id = oci_core_instance_configuration.cluster-network-instance_configuration[0].id

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }

  display_name         = "${local.cluster_name}-fabric1"
  gpu_memory_fabric_id = var.memory_fabric_id
  size                 = var.node_count
}