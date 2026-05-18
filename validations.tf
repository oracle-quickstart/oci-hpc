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
  invalid_federation_config = var.slurm_federation && var.slurm_ha
  invalid_shared_fss_mount_target_ad = (
    var.add_nfs &&
    var.create_fss == "new" &&
    var.mount_target_count == 0 &&
    var.fss_ad != var.ad
  )
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
  compatible_controller_shapes = [for element in data.oci_core_image_shapes.test_controller_image_shapes.image_shape_compatibilities : element.shape]
  compatible_compute_shapes    = [for element in data.oci_core_image_shapes.test_compute_image_shapes.image_shape_compatibilities : element.shape]
  effective_enroot            = var.enroot || var.pyxis
}

#  Validate that slurm_ha is not define with slurm federation

resource "null_resource" "validate_federation_setup" {
  count = local.invalid_federation_config ? 1 : 0
  lifecycle {
    precondition {
      condition     = !local.invalid_federation_config
      error_message = "Error: To join a Slurm Federation, disable 'Create a back-up slurm controller' (slurm_ha)"
    }
  }
}


# validate that the management and compute nodes usernames are set correctly

resource "null_resource" "validate_controller_username" {
  lifecycle {
    precondition {
      condition     = var.controller_username == local.expected_username_controller || local.expected_username_compute == "unknown"
      error_message = "Invalid username for the selected OS on controller. Use 'ubuntu' for Ubuntu images and 'opc' for Oracle Linux images."
    }
  }
}

resource "null_resource" "validate_compute_username" {
  lifecycle {
    precondition {
      condition     = var.compute_username == local.expected_username_compute || local.expected_username_compute == "unknown"
      error_message = "Invalid username for the selected OS on compute nodes. Use 'ubuntu' for Ubuntu images and 'opc' for Oracle Linux images."
    }
  }
}

resource "null_resource" "validate_usernames" {
  lifecycle {
    precondition {
      condition     = var.compute_username == var.controller_username
      error_message = "Using different usernames for controller and compute nodes is not supported."
    }
  }
}

# Validate that Gov/Defense deployments do not point to public OCIR
resource "null_resource" "validate_gov_cloud_registry_choice" {
  lifecycle {
    precondition {
      condition     = !(var.is_gov_cloud && var.use_OCI_generated_container)
      error_message = "In Gov/Defense regions (is_gov_cloud = true), disable 'Point to an existing public OCIR' (use_OCI_generated_container must be false)."
    }
  }
}

# Validate that FSS is created/re-used when using FSS for /home
resource "null_resource" "validate_fss" {
  lifecycle {
    precondition {
      condition     = !(!var.add_nfs && var.shared_home == "fss")
      error_message = "When using FSS for /home, you must create a new FSS or use an existing one."
    }
    precondition {
      condition     = !local.invalid_shared_fss_mount_target_ad
      error_message = "When mount_target_count is 0 and the optional FSS reuses the /config mount target, the optional FSS Availability Domain must match the cluster Availability Domain."
    }
  }
}
