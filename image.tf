resource "oci_core_image" "imported_image" {
  for_each = toset(local.imported_image_urls)

  compartment_id = var.targetCompartment
  display_name   = format("%s-%s", element(split("/", each.value), length(split("/", each.value)) - 1), local.cluster_name)

  image_source_details {
    source_type = "objectStorageUri"
    source_uri  = each.value
  }
}

resource "oci_core_shape_management" "compute-shape" {
  count          = local.effective_compute_image_source == "Marketplace" ? 0 : (local.effective_compute_image_source == "URI" ? 1 : (contains(local.compatible_compute_shapes, local.compute_shape) ? 0 : 1))
  compartment_id = var.targetCompartment
  image_id       = local.compute_image
  shape_name     = local.compute_shape
}


resource "oci_core_shape_management" "controller-shape" {
  count          = var.controller_image_source == "Marketplace" ? 0 : (var.controller_image_source == "URI" ? 1 : (contains(local.compatible_controller_shapes, var.controller_shape) ? 0 : 1))
  compartment_id = var.targetCompartment
  image_id       = local.controller_image
  shape_name     = var.controller_shape
}

data "oci_core_image" "controller_validation" {
  image_id = local.controller_image
}

data "oci_core_image" "compute_validation" {
  image_id = local.compute_image
}

locals {
  detected_username_controller = (
    can(regex("(?i)ubuntu", data.oci_core_image.controller_validation.operating_system)) ? "ubuntu" :
    can(regex("(?i)oracle", data.oci_core_image.controller_validation.operating_system)) ? "opc" :
    "unknown"
  )
  detected_username_compute = (
    can(regex("(?i)ubuntu", data.oci_core_image.compute_validation.operating_system)) ? "ubuntu" :
    can(regex("(?i)oracle", data.oci_core_image.compute_validation.operating_system)) ? "opc" :
    "unknown"
  )

  effective_controller_username = trimspace(var.controller_username) != "" ? var.controller_username : local.detected_username_controller
  effective_compute_username    = var.compute_image_source == "Same as management nodes" ? local.effective_controller_username : trimspace(var.compute_username) != "" ? var.compute_username : local.detected_username_compute

  cluster_admin_user = one(toset([local.effective_compute_username, local.effective_controller_username]))
}
