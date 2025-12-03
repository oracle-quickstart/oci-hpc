# get nodes image IDs

data "oci_core_image" "controller_validation" {
    image_id = local.controller_image
}

data "oci_core_image" "compute_validation" {
    image_id = local.compute_image
}

# get image compatible shapes

data "oci_core_image_shapes" "test_controller_image_shapes" {
    image_id = local.controller_image
}

data "oci_core_image_shapes" "test_compute_image_shapes" {
    image_id = local.compute_image
}


locals {
  invalid_ha_config = !var.add_nfs && var.slurm_ha
  expected_username_controller = (
    can(regex("(?i)ubuntu", data.oci_core_image.controller_validation.operating_system)) ? "ubuntu" :
    can(regex("(?i)oracle", data.oci_core_image.controller_validation.operating_system)) ? "opc" :
    "unknown"
  )
  expected_username_compute = (
    can(regex("(?i)ubuntu", data.oci_core_image.compute_validation.operating_system)) ? "ubuntu" :
    can(regex("(?i)oracle", data.oci_core_image.compute_validation.operating_system)) ? "opc" :
    "unknown"
  )
  compatible_controller_shapes = [ for element in data.oci_core_image_shapes.test_controller_image_shapes.image_shape_compatibilities : element.shape ]
  compatible_compute_shapes = [ for element in data.oci_core_image_shapes.test_compute_image_shapes.image_shape_compatibilities : element.shape ]
}


#  Validate that FSS is present to host the slurm database

resource "null_resource" "validate_ha_setup" {
  count = local.invalid_ha_config ? 1 : 0
  lifecycle {
    precondition {
      condition     = !local.invalid_ha_config
      error_message = "Error: Slurm HA configuration requires a shared NFS. Add NFS or create FSS (create_fss = true). "
    }
  }
}

# validate that the management and compute nodes usernames are set correctly

resource "null_resource" "validate_controller_username" {
  lifecycle {
    precondition {
      condition     = var.controller_username == local.expected_username_controller
      error_message = "Invalid username for the selected OS on controller. Use 'ubuntu' for Ubuntu images and 'opc' for Oracle Linux images."
    }
  }
}

resource "null_resource" "validate_compute_username" {
  lifecycle {
    precondition {
      condition     = var.compute_username == local.expected_username_compute
      error_message = "Invalid username for the selected OS on compute nodes. Use 'ubuntu' for Ubuntu images and 'opc' for Oracle Linux images."
    }
  }
}

# validate that the images are compatible with the node CPU architecture (x86_64 versus aarch64)

resource "null_resource" "validate_controller_compatibility" {
  lifecycle {
    precondition {
      condition     = contains(local.compatible_controller_shapes, var.controller_shape)
      error_message = "Selected controller image is not compatible with the controller shape CPU architecture."
    }
  }
}

resource "null_resource" "validate_cluster_network_compatibility" {
  count = var.rdma_enabled ? 1 : 0
  lifecycle {
    precondition {
      condition     = contains(local.compatible_compute_shapes, var.cluster_network_shape)
      error_message = "Selected compute image is not compatible with the compute node shape CPU architecture."
    }
  }
}

resource "null_resource" "validate_instance_pool_compatibility" {
  count = !var.rdma_enabled ? 1 : 0
  lifecycle {
    precondition {
      condition     = contains(local.compatible_compute_shapes, var.instance_pool_shape)
      error_message = "Selected compute image is not compatible with the compute node shape CPU architecture."
    }
  }
}