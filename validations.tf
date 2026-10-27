
# get image compatible shapes

data "oci_core_image_shapes" "test_controller_image_shapes" {
  image_id = local.controller_image
}

data "oci_core_image_shapes" "test_compute_image_shapes" {
  image_id = local.compute_image
}


locals {
  # Leave 20% free beyond an image's required size so normal image growth does
  # not turn a previously valid boot-volume setting into a launch-time error.
  boot_volume_safety_coefficient = 1.20
  boot_volume_minimums = {
    controller = ceil(tonumber(data.oci_core_image.controller_validation.size_in_mbs) / 1024 * local.boot_volume_safety_coefficient)
    compute    = ceil(tonumber(data.oci_core_image.compute_validation.size_in_mbs) / 1024 * local.boot_volume_safety_coefficient)
  }
  boot_volume_checks = {
    controller = { enabled = true, requested = var.controller_boot_volume_size, minimum = local.boot_volume_minimums.controller }
    compute    = { enabled = var.node_count > 0, requested = var.boot_volume_size, minimum = local.boot_volume_minimums.compute }
    login      = { enabled = var.login_node, requested = var.login_boot_volume_size, minimum = local.boot_volume_minimums.controller }
    monitoring = { enabled = var.monitoring_node, requested = var.monitoring_boot_volume_size, minimum = local.boot_volume_minimums.controller }
  }

  invalid_federation_config = var.slurm_federation && var.slurm_ha
  invalid_dgxc_config       = var.dgxc_benchmarking && (!var.slurm || !var.pyxis)
  invalid_shared_fss_mount_target_ad = (
    var.add_nfs &&
    var.create_fss == "new" &&
    var.mount_target_count == 0 &&
    var.fss_ad != var.ad
  )
  compatible_controller_shapes = [for element in data.oci_core_image_shapes.test_controller_image_shapes.image_shape_compatibilities : element.shape]
  compatible_compute_shapes    = [for element in data.oci_core_image_shapes.test_compute_image_shapes.image_shape_compatibilities : element.shape]

  controller_image_unlisted_ocid_set = try(trimspace(var.controller_image_unlisted_ocid), "") != ""
  controller_image_ocid_set          = try(trimspace(var.controller_image_ocid), "") != ""
  controller_image_uri_set           = try(trimspace(var.controller_image_uri), "") != ""
  compute_image_unlisted_ocid_set    = try(trimspace(var.compute_image_unlisted_ocid), "") != ""
  compute_image_ocid_set             = try(trimspace(var.compute_image_ocid), "") != ""
  compute_image_uri_set              = try(trimspace(var.compute_image_uri), "") != ""

  valid_controller_image_source_inputs = (
    var.controller_image_source == "Marketplace" ? !local.controller_image_unlisted_ocid_set && !local.controller_image_ocid_set && !local.controller_image_uri_set :
    var.controller_image_source == "Unlisted" ? local.controller_image_unlisted_ocid_set && !local.controller_image_ocid_set && !local.controller_image_uri_set :
    var.controller_image_source == "Custom" ? local.controller_image_ocid_set && !local.controller_image_unlisted_ocid_set && !local.controller_image_uri_set :
    var.controller_image_source == "URI" ? local.controller_image_uri_set && !local.controller_image_unlisted_ocid_set && !local.controller_image_ocid_set :
    false
  )
  valid_compute_image_source_inputs = (
    var.compute_image_source == "Same as management nodes" ? !local.compute_image_unlisted_ocid_set && !local.compute_image_ocid_set && !local.compute_image_uri_set :
    var.compute_image_source == "Marketplace" ? !local.compute_image_unlisted_ocid_set && !local.compute_image_ocid_set && !local.compute_image_uri_set :
    var.compute_image_source == "Unlisted" ? local.compute_image_unlisted_ocid_set && !local.compute_image_ocid_set && !local.compute_image_uri_set :
    var.compute_image_source == "Custom" ? local.compute_image_ocid_set && !local.compute_image_unlisted_ocid_set && !local.compute_image_uri_set :
    var.compute_image_source == "URI" ? local.compute_image_uri_set && !local.compute_image_unlisted_ocid_set && !local.compute_image_ocid_set :
    false
  )
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

resource "null_resource" "validate_dgxc_benchmarking" {
  count = local.invalid_dgxc_config ? 1 : 0
  lifecycle {
    precondition {
      condition     = !local.invalid_dgxc_config
      error_message = "DGXC benchmarking requires slurm=true and pyxis=true. Enroot is configured by the standard Enroot/Pyxis playbooks."
    }
  }
}


# validate that the management and compute nodes usernames are set correctly

resource "null_resource" "validate_controller_username" {
  lifecycle {
    precondition {
      condition     = local.effective_controller_username == local.detected_username_controller || local.detected_username_compute == "unknown"
      error_message = "Invalid username for the selected OS on controller. Use 'ubuntu' for Ubuntu images and 'opc' for Oracle Linux images."
    }
  }
}

resource "null_resource" "validate_compute_username" {
  lifecycle {
    precondition {
      condition     = local.effective_compute_username == local.detected_username_compute || local.detected_username_compute == "unknown"
      error_message = "Invalid username for the selected OS on compute nodes. Use 'ubuntu' for Ubuntu images and 'opc' for Oracle Linux images."
    }
  }
}

resource "null_resource" "validate_controller_image_source_inputs" {
  lifecycle {
    precondition {
      condition     = local.valid_controller_image_source_inputs
      error_message = "Set only the management image field that matches controller_image_source. Marketplace requires controller_image_unlisted_ocid, controller_image_ocid, and controller_image_uri to be unset; Unlisted requires only controller_image_unlisted_ocid; Custom requires only controller_image_ocid; URI requires only controller_image_uri."
    }
  }
}

resource "null_resource" "validate_compute_image_source_inputs" {
  lifecycle {
    precondition {
      condition     = local.valid_compute_image_source_inputs
      error_message = "Set only the compute image field that matches compute_image_source. Marketplace requires compute_image_unlisted_ocid, compute_image_ocid, and compute_image_uri to be unset; Unlisted requires only compute_image_unlisted_ocid; Custom requires only compute_image_ocid; URI requires only compute_image_uri."
    }
  }
}

# Marketplace images cannot have compatible shapes added. Validate optional
# management-image roles before launching their instances. Custom and imported
# images are handled by the corresponding shape-management resources.
resource "null_resource" "validate_management_role_image_shapes" {
  lifecycle {
    precondition {
      condition     = var.controller_image_source != "Marketplace" || !var.login_node || contains(local.compatible_controller_shapes, var.login_shape)
      error_message = "login_shape is not compatible with the selected marketplace management image. Select a compatible login shape or use a custom/imported image."
    }

    precondition {
      condition     = var.controller_image_source != "Marketplace" || !var.monitoring_node || contains(local.compatible_controller_shapes, var.monitoring_shape)
      error_message = "monitoring_shape is not compatible with the selected marketplace management image. Select a compatible monitoring shape or use a custom/imported image."
    }

    precondition {
      condition     = var.controller_image_source != "Marketplace" || !var.slurm_ha || contains(local.compatible_controller_shapes, var.controller_shape)
      error_message = "controller_shape is not compatible with the selected marketplace management image for the Slurm backup controller. Select a compatible controller shape."
    }
  }
}

# Validate image-dependent boot-volume sizes before any instance or instance
# configuration is created. OCI returns the image minimum only at launch time;
# retain 20% headroom to make that requirement resilient to image updates.
resource "null_resource" "validate_boot_volume_sizes" {
  for_each = { for role, check in local.boot_volume_checks : role => check if check.enabled }

  lifecycle {
    precondition {
      condition     = each.value.requested >= each.value.minimum
      error_message = "${each.key} boot volume size must be at least ${each.value.minimum} GB (the selected image size plus 20% safety headroom)."
    }
  }
}

resource "null_resource" "validate_usernames" {
  lifecycle {
    precondition {
      condition     = var.compute_image_source == "Same as management nodes" || var.compute_username == var.controller_username
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
    precondition {
      condition     = !var.add_nfs || var.create_fss == "new" || trimspace(var.nfs_source_IP) != ""
      error_message = "When add_nfs is true and create_fss is not 'new', nfs_source_IP must be set."
    }
  }
}
