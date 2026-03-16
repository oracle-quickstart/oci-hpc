resource "oci_core_shape_management" "compute-shape" {
    count = contains(local.compatible_compute_shapes, var.rdma_enabled ? var.cluster_network_shape : var.instance_pool_shape) ? 0 : 1
    compartment_id = var.targetCompartment
    image_id = local.compute_image
    shape_name = var.rdma_enabled ? var.cluster_network_shape : var.instance_pool_shape
}


resource "oci_core_shape_management" "controller-shape" {
    count = contains(local.compatible_controller_shapes, var.controller_shape) ? 0 : 1
    compartment_id = var.targetCompartment
    image_id = local.controller_image
    shape_name = var.controller_shape
}