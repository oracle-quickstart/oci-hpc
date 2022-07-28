locals { 
// display names of instances 
  cluster_instances_ids = var.cluster_network ? data.oci_core_instance.cluster_network_instances.*.id : data.oci_core_instance.instance_pool_instances.*.id
  cluster_instances_names = var.cluster_network ? data.oci_core_instance.cluster_network_instances.*.display_name : data.oci_core_instance.instance_pool_instances.*.display_name

  image_ocid = var.unsupported ? var.image_ocid : var.image
  custom_bastion_image_ocid = var.unsupported_bastion ? var.unsupported_bastion_image : var.custom_bastion_image

// ips of the instances
  cluster_instances_ips = var.cluster_network ? data.oci_core_instance.cluster_network_instances.*.private_ip : data.oci_core_instance.instance_pool_instances.*.private_ip

// vcn id derived either from created vcn or existing if specified
  vcn_id = var.use_existing_vcn ? var.vcn_id : element(concat(oci_core_vcn.vcn.*.id, [""]), 0)

// subnet id derived either from created subnet or existing if specified
//  subnet_id = var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0)
  subnet_id = var.private_deployment ? var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 1) : var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0)

  nfs_source_IP = var.create_fss ? element(concat(oci_file_storage_mount_target.FSSMountTarget.*.ip_address, [""]), 0) : var.nfs_source_IP
// subnet id derived either from created subnet or existing if specified
// bastion_subnet_id = var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.public-subnet.*.id, [""]), 0)
  bastion_subnet_id = var.private_deployment ? var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0) : var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.public-subnet.*.id, [""]), 0)
  
  cluster_name = var.use_custom_name ? var.cluster_name : random_pet.name.id

  bastion_image = var.use_standard_image ? oci_core_app_catalog_subscription.bastion_mp_image_subscription[0].listing_resource_id : local.custom_bastion_image_ocid

  cluster_network_image = var.use_marketplace_image ? oci_core_app_catalog_subscription.mp_image_subscription[0].listing_resource_id : local.image_ocid

  instance_pool_image = ! var.cluster_network && var.use_marketplace_image ? oci_core_app_catalog_subscription.mp_image_subscription[0].listing_resource_id : local.image_ocid

//  image = (var.cluster_network && var.use_marketplace_image == true) || (var.cluster_network == false && var.use_marketplace_image == false) ? var.image : data.oci_core_images.linux.images.0.id

  is_bastion_flex_shape = length(regexall(".*VM.*.*Flex$", var.bastion_shape)) > 0 ? [var.bastion_ocpus]:[]
  is_instance_pool_flex_shape = length(regexall(".*VM.*.*Flex$", var.instance_pool_shape)) > 0 ? [var.instance_pool_ocpus]:[]

  bastion_mount_ip = var.bastion_block ? element(concat(oci_core_volume_attachment.bastion_volume_attachment.*.ipv4, [""]), 0) : "none"

  scratch_nfs_type = var.cluster_network ? var.scratch_nfs_type_cluster : var.scratch_nfs_type_pool 

  iscsi_ip = var.cluster_network ? element(concat(oci_core_volume_attachment.cluster_network_volume_attachment.*.ipv4, [""]), 0) : element(concat(oci_core_volume_attachment.instance_pool_volume_attachment.*.ipv4, [""]), 0)

  mount_ip = local.scratch_nfs_type == "block" ? local.iscsi_ip : "none" 

// Cluster OCID


  cluster_ocid = var.node_count > 0 ? var.cluster_network ? oci_core_cluster_network.cluster_network[0].id : oci_core_instance_pool.instance_pool[0].id : ""
  host = var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip[0].ip_address : oci_core_instance.bastion.public_ip
  bastion_bool_ip = var.private_deployment ? false : true
  bastion_subnet = var.private_deployment ? oci_core_subnet.private-subnet : oci_core_subnet.private-subnet 
  private_subnet_cidr = var.private_deployment ? [var.public_subnet, var.private_subnet] : [var.private_subnet]
  host_backup = var.slurm_ha ? var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip_backup[0].ip_address : oci_core_instance.backup[0].public_ip : "none"
}
