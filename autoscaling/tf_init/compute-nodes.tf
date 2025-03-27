resource "random_string" "cc_name" {
  count = var.compute_cluster ? var.node_count : 0
  length = 5
  lower  = true
  numeric = false
  special = false
}

resource "oci_core_instance" "compute_cluster_instances" {
  count = var.compute_cluster ? var.node_count : 0
  depends_on          = [oci_core_compute_cluster.compute_cluster]
  availability_domain = var.ad
  compartment_id      = var.targetCompartment
  shape               = var.cluster_network_shape

  agent_config {
    is_management_disabled = true
    }

  display_name        = "inst-" + random_string.cc_name[count.index].result + "-${local.cluster_name}"

  freeform_tags = {
    "cluster_name" = local.cluster_name
    "controller_name" = var.controller_name
    "user" = var.tags
    "hostname_convention" = var.hostname_convention
  }

  metadata = {
    ssh_authorized_keys = file("/home/${var.controller_username}/.ssh/ed25519.pub")
    user_data           = base64encode(file("cloud-init.sh"))
  }
  source_details {
    source_id = local.cluster_network_image
    source_type             = "image"
    boot_volume_size_in_gbs = var.boot_volume_size
  }
  compute_cluster_id=length(var.compute_cluster_id) > 2 ? var.compute_cluster_id : oci_core_compute_cluster.compute_cluster[0].id
  create_vnic_details {
    subnet_id = local.subnet_id
    assign_public_ip = false
  }
} 