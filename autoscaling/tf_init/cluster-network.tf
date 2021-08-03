resource "oci_core_volume" "nfs-cluster-network-volume" { 
  count = var.scratch_nfs_type_cluster == "block" && var.node_count > 0 ? 1 : 0 
  availability_domain = var.ad
  compartment_id = var.targetCompartment
  display_name = "${local.cluster_name}-nfs-volume"
  
  size_in_gbs = var.cluster_block_volume_size
  vpus_per_gb = split(".", var.cluster_block_volume_performance)[0]
}

resource "oci_core_volume_attachment" "cluster_network_volume_attachment" { 
  count = var.scratch_nfs_type_cluster == "block" && var.node_count > 0 ? 1 : 0 
  attachment_type = "iscsi"
  volume_id       = oci_core_volume.nfs-cluster-network-volume[0].id
  instance_id     = local.cluster_instances_ids[0]
  display_name    = "${local.cluster_name}-cluster-network-volume-attachment"
  device          = "/dev/oracleoci/oraclevdb"
} 

resource "oci_core_cluster_network" "cluster_network" {
  count = var.cluster_network && var.node_count > 0 ? 1 : 0
  depends_on     = [oci_core_app_catalog_subscription.mp_image_subscription, oci_core_subnet.private-subnet, oci_core_subnet.public-subnet]
  compartment_id = var.targetCompartment
  instance_pools {
    instance_configuration_id = oci_core_instance_configuration.cluster-network-instance_configuration[0].id
    size                      = var.node_count
    display_name              = local.cluster_name
  }
  placement_configuration {
    availability_domain = var.ad
    primary_subnet_id   = local.subnet_id
  }
  timeouts {
    create = "180m"
  }
  display_name = local.cluster_name
}

