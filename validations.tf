data "oci_core_image" "controller_validation" {
    image_id = local.controller_image
}

data "oci_core_image" "compute_validation" {
    image_id = local.compute_image
}

data "oci_core_image" "login_validation" {
    count               = var.login_node ? 1 : 0
    image_id = local.controller_image
}

data "oci_core_image" "monitoring_validation" {
    count               = var.monitoring_node ? 1 : 0
    image_id = local.controller_image
}


locals {
  invalid_ha_config = !var.add_nfs && var.slurm_ha
  expected_username_controller = (
    can(regex("(?i)ubuntu", data.oci_core_image.controller_validation.operating_system)) ? "ubuntu" :
    can(regex("(?i)oracle", data.oci_core_image.controller_validation.operating_system)) ? "opc" :
    "unknown"
  )  
  expected_username_login = (
    can(regex("(?i)ubuntu", data.oci_core_image.login_validation[0].operating_system)) ? "ubuntu" :
    can(regex("(?i)oracle", data.oci_core_image.login_validation[0].operating_system)) ? "opc" :
    "unknown"
  )
  expected_username_monitoring = (
    can(regex("(?i)ubuntu", data.oci_core_image.monitoring_validation[0].operating_system)) ? "ubuntu" :
    can(regex("(?i)oracle", data.oci_core_image.monitoring_validation[0].operating_system)) ? "opc" :
    "unknown"
  )  
  expected_username_compute = (
    can(regex("(?i)ubuntu", data.oci_core_image.compute_validation.operating_system)) ? "ubuntu" :
    can(regex("(?i)oracle", data.oci_core_image.compute_validation.operating_system)) ? "opc" :
    "unknown"
  )  
  
}


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

resource "null_resource" "validate_login_username" {
  count               = var.login_node ? 1 : 0
  lifecycle {
    precondition {
      condition     = var.controller_username == local.expected_username_login
      error_message = "Invalid username for the selected OS on login node. Use 'ubuntu' for Ubuntu images and 'opc' for Oracle Linux images."
    }
  }
}

resource "null_resource" "validate_monitoring_username" {
  count               = var.monitoring_node ? 1 : 0
  lifecycle {
    precondition {
      condition     = var.controller_username == local.expected_username_monitoring
      error_message = "Invalid username for the selected OS on monitoring node. Use 'ubuntu' for Ubuntu images and 'opc' for Oracle Linux images."
    }
  }  
}




resource "null_resource" "validate_ha_setup" {
  count = local.invalid_ha_config ? 1 : 0

  lifecycle {
    precondition {
      condition     = !local.invalid_ha_config
      error_message = "Error: Slurm HA configuration requires a shared NFS. Add NFS or create FSS (create_fss = true). "
    }
  }
}