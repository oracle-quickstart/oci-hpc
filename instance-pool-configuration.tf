resource "oci_core_instance_configuration" "instance_pool_configuration" {
  count = ( ! var.cluster_network ) && ( var.node_count > 0 ) ? 1 : 0
  depends_on     = [oci_core_app_catalog_subscription.mp_image_subscription]
  compartment_id = var.targetCompartment
  display_name   = local.cluster_name

  instance_details {
    instance_type = "compute"
    launch_details {
      availability_domain = var.ad
      compartment_id      = var.targetCompartment
      create_vnic_details {
      }
      display_name = local.cluster_name
      freeform_tags = {
        "cluster_name" = local.cluster_name
        "parent_cluster" = local.cluster_name
      }
      metadata = {
# TODO: add user key to the authorized_keys 
        ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
        user_data           = base64encode(data.template_file.config.rendered)
      }
      agent_config {
        is_management_disabled = true
        }
      shape = var.instance_pool_shape

      dynamic "shape_config" {
        for_each = local.is_instance_pool_flex_shape
          content {
            ocpus = shape_config.value
            memory_in_gbs = var.instance_pool_custom_memory ? var.instance_pool_memory : 16 * shape_config.value
          }
      }
  
      source_details {
        source_type             = "image"
        boot_volume_size_in_gbs = var.boot_volume_size
        image_id                = local.instance_pool_image
      }
    }
  }

  source = "NONE"
}

