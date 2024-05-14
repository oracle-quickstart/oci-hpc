resource "oci_core_instance_configuration" "instance_pool_configuration" {
  count = var.cluster_network ? 0 : 1
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
      metadata = {
# TODO: add user key to the authorized_keys 
        ssh_authorized_keys = file("/home/${var.controller_username}/.ssh/id_rsa.pub")
        user_data           = base64encode(data.template_file.config.rendered)
      }
      agent_config {

        are_all_plugins_disabled = false
        is_management_disabled   = true
        is_monitoring_disabled   = false

        plugins_config {
          desired_state = "DISABLED"
          name          = "OS Management Service Agent"
          }
        dynamic plugins_config {
          for_each = length(regexall(".*GPU.*", var.instance_pool_shape)) > 0 ? ["ENABLED"] : ["DISABLED"]
          content {
          name = "Compute RDMA GPU Monitoring"
          desired_state = plugins_config.value
          }
        }
      }
      shape = var.instance_pool_shape

      dynamic "shape_config" {
        for_each = local.is_instance_pool_flex_shape
          content {
            ocpus = shape_config.value
            memory_in_gbs = var.instance_pool_custom_memory ? var.instance_pool_memory : 16 * shape_config.value
          }
      }
      dynamic "platform_config" {
        for_each = var.BIOS ? range(1) : []
        content {
          type = local.platform_type
          are_virtual_instructions_enabled = var.virt_instr
          is_access_control_service_enabled = var.access_ctrl
          is_input_output_memory_management_unit_enabled = var.IOMMU
          is_symmetric_multi_threading_enabled = var.SMT
          numa_nodes_per_socket = var.numa_nodes_per_socket == "Default" ? (local.platform_type == "GENERIC_BM" ? "NPS1": "NPS4" ): var.numa_nodes_per_socket
          percentage_of_cores_enabled = var.percentage_of_cores_enabled == "Default" ? 100 : tonumber(var.percentage_of_cores_enabled)
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

