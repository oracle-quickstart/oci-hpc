resource "random_string" "cc_name" {
  count = var.compute_cluster ? var.node_count : 0
  length = 5
  lower  = true
  numeric = false
  special = false
}

resource "oci_core_instance" "compute_cluster_instances" {
  count               = var.compute_cluster ? var.node_count : 0
  depends_on          = [oci_core_compute_cluster.compute_cluster, oci_functions_function.function]
  availability_domain = var.ad
  compartment_id      = var.targetCompartment
  shape               = var.cluster_network_shape

  agent_config {

    are_all_plugins_disabled = false
    is_management_disabled   = true
    is_monitoring_disabled   = false

    plugins_config {
      desired_state = "DISABLED"
      name          = "OS Management Service Agent"
    }
    dynamic "plugins_config" {

      for_each = var.cluster_network ? ["ENABLED"] : ["DISABLED"]
      content {
        name          = "Compute HPC RDMA Authentication"
        desired_state = plugins_config.value
      }
    }
    dynamic "plugins_config" {
      for_each = var.cluster_network ? ["ENABLED"] : ["DISABLED"]
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
    "cluster_name"   = local.cluster_name
    "controller_name" = oci_core_instance.controller.display_name
    "hostname_convention" = var.hostname_convention
  }

  metadata = {
    ssh_authorized_keys = var.compute_node_ssh_key == "" ? "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}" : "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}${var.compute_node_ssh_key}\n"
    user_data           = base64encode(file("cloud-init.sh"))
  }
  source_details {
    source_id               = local.cluster_network_image
    source_type             = "image"
    boot_volume_size_in_gbs = var.boot_volume_size
    boot_volume_vpus_per_gb = 30
  }
  compute_cluster_id = length(var.compute_cluster_id) > 2 ? var.compute_cluster_id : oci_core_compute_cluster.compute_cluster[0].id
  create_vnic_details {
    subnet_id        = local.subnet_id
    assign_public_ip = false
  }
}