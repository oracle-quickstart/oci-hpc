resource "random_string" "cc_name" {
  count   = var.stand_alone ? var.node_count : 0
  length  = 5
  lower   = true
  numeric = false
  special = false
}

resource "oci_core_instance" "compute_cluster_instances" {
  count               = var.stand_alone && var.rdma_enabled ? var.node_count : 0
  depends_on          = [oci_core_compute_cluster.compute_cluster, oci_functions_function.function, null_resource.cluster]
  availability_domain = var.ad
  compartment_id      = var.targetCompartment
  shape               = var.cluster_network_shape
  instance_options {

    are_legacy_imds_endpoints_disabled = true
  
  }
  agent_config {

    are_all_plugins_disabled = false
    is_management_disabled   = true
    is_monitoring_disabled   = false

    plugins_config {
      desired_state = "DISABLED"
      name          = "OS Management Service Agent"
    }
    dynamic "plugins_config" {

      for_each = var.rdma_enabled ? ["ENABLED"] : ["DISABLED"]
      content {
        name          = "Compute HPC RDMA Authentication"
        desired_state = plugins_config.value
      }
    }
    dynamic "plugins_config" {
      for_each = var.rdma_enabled ? ["ENABLED"] : ["DISABLED"]
      content {
        name          = "Compute HPC RDMA Auto-Configuration"
        desired_state = plugins_config.value
      }
    }
    dynamic "plugins_config" {
      for_each = length(regexall(".*GPU.*", var.cluster_network_shape)) > 0 ? ["ENABLED"] : ["DISABLED"]
      content {
        name          = "Compute RDMA GPU Monitoring"
        desired_state = plugins_config.value
      }
    }
  }

  display_name = "inst-${random_string.cc_name[count.index].result}-${local.cluster_name}"

  freeform_tags = {
    "cluster_name"        = local.cluster_name
    "controller_name"     = oci_core_instance.controller.display_name
    "hostname_convention" = var.hostname_convention
  }

  metadata = {
    ssh_authorized_keys = var.compute_node_ssh_key == "" ? "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}" : "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}${var.compute_node_ssh_key}\n"
    user_data           = base64encode(file("cloud-init.sh"))
  }
  source_details {
    source_id               = local.compute_image
    source_type             = "image"
    boot_volume_size_in_gbs = var.boot_volume_size
    boot_volume_vpus_per_gb = 30
  }
  compute_cluster_id = length(var.compute_cluster_id) > 2 ? var.compute_cluster_id : oci_core_compute_cluster.compute_cluster[0].id
  create_vnic_details {
    subnet_id        = local.subnet_id
    assign_public_ip = false
  }
  dynamic "platform_config" {
    for_each = var.BIOS ? range(1) : []
    content {
      type                                           = local.platform_type
      are_virtual_instructions_enabled               = var.virt_instr
      is_access_control_service_enabled              = var.access_ctrl
      is_input_output_memory_management_unit_enabled = var.IOMMU
      is_symmetric_multi_threading_enabled           = var.SMT
      numa_nodes_per_socket                          = var.numa_nodes_per_socket == "Default" ? (local.platform_type == "GENERIC_BM" ? "NPS1" : "NPS4") : var.numa_nodes_per_socket
      percentage_of_cores_enabled                    = var.percentage_of_cores_enabled == "Default" ? 100 : tonumber(var.percentage_of_cores_enabled)
    }
  }
}

resource "oci_core_instance" "compute_instances" {
  count               = var.stand_alone && (!var.rdma_enabled) ? var.node_count : 0
  depends_on          = [oci_functions_function.function, null_resource.cluster]
  availability_domain = var.ad
  compartment_id      = var.targetCompartment
  shape               = var.instance_pool_shape
  dynamic "shape_config" {
    for_each = local.is_instance_pool_flex_shape
    content {
      ocpus         = shape_config.value
      memory_in_gbs = var.instance_pool_custom_memory ? var.instance_pool_memory : 16 * shape_config.value
    }
  }
  agent_config {

    are_all_plugins_disabled = false
    is_management_disabled   = true
    is_monitoring_disabled   = false

    plugins_config {
      desired_state = "DISABLED"
      name          = "OS Management Service Agent"
    }
    dynamic "plugins_config" {

      for_each = var.rdma_enabled ? ["ENABLED"] : ["DISABLED"]
      content {
        name          = "Compute HPC RDMA Authentication"
        desired_state = plugins_config.value
      }
    }
    dynamic "plugins_config" {
      for_each = var.rdma_enabled ? ["ENABLED"] : ["DISABLED"]
      content {
        name          = "Compute HPC RDMA Auto-Configuration"
        desired_state = plugins_config.value
      }
    }
    dynamic "plugins_config" {
      for_each = length(regexall(".*GPU.*", var.cluster_network_shape)) > 0 ? ["ENABLED"] : ["DISABLED"]
      content {
        name          = "Compute RDMA GPU Monitoring"
        desired_state = plugins_config.value
      }
    }
  }

  dynamic "preemptible_instance_config" {
    for_each = var.preemptible ? [1] : []
    content {
      preemption_action {
        type                 = "TERMINATE"
        preserve_boot_volume = false
      }
    }
  }

  display_name = "inst-${random_string.cc_name[count.index].result}-${local.cluster_name}"

  freeform_tags = {
    "cluster_name"        = local.cluster_name
    "controller_name"     = oci_core_instance.controller.display_name
    "hostname_convention" = var.hostname_convention
  }

  metadata = {
    ssh_authorized_keys = var.compute_node_ssh_key == "" ? "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}" : "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}${var.compute_node_ssh_key}\n"
    user_data           = base64encode(file("cloud-init.sh"))
  }
  source_details {
    source_id               = local.compute_image
    source_type             = "image"
    boot_volume_size_in_gbs = var.boot_volume_size
    boot_volume_vpus_per_gb = 30
  }
  create_vnic_details {
    subnet_id        = local.subnet_id
    assign_public_ip = false
  }
}
