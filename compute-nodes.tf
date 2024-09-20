resource "oci_core_volume" "nfs-compute-cluster-volume" {
  count               = var.compute_cluster && var.scratch_nfs_type_cluster == "block" && var.node_count > 0 ? 1 : 0
  availability_domain = var.ad
  compartment_id      = var.targetCompartment
  display_name        = "${local.cluster_name}-nfs-volume"

  size_in_gbs = var.cluster_block_volume_size
  vpus_per_gb = split(".", var.cluster_block_volume_performance)[0]
}

resource "oci_core_volume_attachment" "compute_cluster_volume_attachment" {
  count           = var.compute_cluster && var.scratch_nfs_type_cluster == "block" && var.node_count > 0 ? 1 : 0
  attachment_type = "iscsi"
  volume_id       = oci_core_volume.nfs-compute-cluster-volume[0].id
  instance_id     = oci_core_instance.compute_cluster_instances[0].id
  display_name    = "${local.cluster_name}-compute-cluster-volume-attachment"
  device          = "/dev/oracleoci/oraclevdb"
}

resource "oci_core_instance" "compute_cluster_instances" {
  count               = var.compute_cluster ? var.node_count : 0
  depends_on          = [oci_core_compute_cluster.compute_cluster]
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

      for_each = var.use_compute_agent ? ["ENABLED"] : ["DISABLED"]
      content {
        name          = "Compute HPC RDMA Authentication"
        desired_state = plugins_config.value
      }
    }
    dynamic "plugins_config" {
      for_each = var.use_compute_agent ? ["ENABLED"] : ["DISABLED"]
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

  display_name = "${local.cluster_name}-node-${var.compute_cluster_start_index + count.index}"

  freeform_tags = {
    "cluster_name"   = local.cluster_name
    "parent_cluster" = local.cluster_name
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
    user_data           = base64encode(data.template_file.controller_config.rendered)
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