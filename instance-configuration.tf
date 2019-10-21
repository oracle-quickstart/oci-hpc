data "template_file" "config" {
  template = file("config.hpc")
}

resource "oci_core_instance_configuration" "instance_configuration" {
  depends_on     = [oci_core_app_catalog_subscription.mp_image_subscription]
  compartment_id = var.compartment_ocid
  display_name   = local.cluster_name

  instance_details {
    instance_type = "compute"
    launch_details {
      availability_domain = var.ad
      compartment_id      = var.compartment_ocid
      create_vnic_details {
      }
      display_name = local.cluster_name
      metadata = {
        ssh_authorized_keys = tls_private_key.ssh.public_key_openssh
        user_data           = base64encode(data.template_file.config.rendered)
      }
      shape = var.shape
      source_details {
        source_type             = "image"
        boot_volume_size_in_gbs = 700
        image_id                = var.image
      }
    }
  }

  source = "NONE"
}

