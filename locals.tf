locals { 
// display names of instances 
  cluster_instances_ids = var.compute_cluster ? oci_core_instance.compute_cluster_instances.*.id : var.cluster_network ? data.oci_core_instance.cluster_network_instances.*.id : data.oci_core_instance.instance_pool_instances.*.id
  cluster_instances_names = var.compute_cluster ? oci_core_instance.compute_cluster_instances.*.display_name : var.cluster_network ? data.oci_core_instance.cluster_network_instances.*.display_name : data.oci_core_instance.instance_pool_instances.*.display_name

  image_ocid = var.unsupported ? var.image_ocid : var.image
  custom_controller_image_ocid = var.unsupported_controller ? var.unsupported_controller_image : var.custom_controller_image
  custom_login_image_ocid = var.unsupported_login ? var.unsupported_login_image : var.custom_login_image

  shape = var.cluster_network ? var.cluster_network_shape : var.instance_pool_shape
  instance_pool_ocpus = ( local.shape == "VM.DenseIO.E4.Flex" || local.shape == "VM.DenseIO.E5.Flex" ) ? var.instance_pool_ocpus_denseIO_flex : var.instance_pool_ocpus
  controller_ocpus = ( var.controller_shape == "VM.DenseIO.E4.Flex" || var.controller_shape == "VM.DenseIO.E5.Flex" ) ? var.controller_ocpus_denseIO_flex : var.controller_ocpus
  login_ocpus = ( var.login_shape == "VM.DenseIO.E4.Flex" || var.login_shape == "VM.DenseIO.E5.Flex" ) ? var.login_ocpus_denseIO_flex : var.login_ocpus
// ips of the instances
  cluster_instances_ips = var.compute_cluster ? oci_core_instance.compute_cluster_instances.*.private_ip : var.cluster_network ? data.oci_core_instance.cluster_network_instances.*.private_ip : data.oci_core_instance.instance_pool_instances.*.private_ip

// vcn id derived either from created vcn or existing if specified
  vcn_id = var.use_existing_vcn ? var.vcn_id : element(concat(oci_core_vcn.vcn.*.id, [""]), 0)

// subnet id derived either from created subnet or existing if specified
//  subnet_id = var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0)
  subnet_id = var.private_deployment ? var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 1) : var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0)

  nfs_source_IP = var.create_fss ? element(concat(oci_file_storage_mount_target.FSSMountTarget.*.ip_address, [""]), 0) : var.nfs_source_IP
// subnet id derived either from created subnet or existing if specified
// controller_subnet_id = var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.public-subnet.*.id, [""]), 0)
  controller_subnet_id = var.private_deployment ? var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0) : var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.public-subnet.*.id, [""]), 0)
  
  cluster_name = var.use_custom_name ? var.cluster_name : random_pet.name.id

  controller_image = var.use_marketplace_image_controller ? oci_core_app_catalog_subscription.controller_mp_image_subscription[0].listing_resource_id : local.custom_controller_image_ocid

  login_image = var.login_node &&  var.use_marketplace_image_login ? oci_core_app_catalog_subscription.login_mp_image_subscription[0].listing_resource_id : local.custom_login_image_ocid

  cluster_network_image = var.use_marketplace_image ? oci_core_app_catalog_subscription.mp_image_subscription[0].listing_resource_id : local.image_ocid

  instance_pool_image = ! var.cluster_network && var.use_marketplace_image ? oci_core_app_catalog_subscription.mp_image_subscription[0].listing_resource_id : local.image_ocid

//  image = (var.cluster_network && var.use_marketplace_image == true) || (var.cluster_network == false && var.use_marketplace_image == false) ? var.image : data.oci_core_images.linux.images.0.id

  is_controller_flex_shape = length(regexall(".*VM.*.*Flex$", var.controller_shape)) > 0 ? [local.controller_ocpus]:[]
  is_login_flex_shape = length(regexall(".*VM.*.*Flex$", var.login_shape)) > 0 ? [local.login_ocpus]:[]

  is_instance_pool_flex_shape = length(regexall(".*VM.*.*Flex$", var.instance_pool_shape)) > 0 ? [local.instance_pool_ocpus]:[]
  
  controller_mount_ip = var.controller_block ? element(concat(oci_core_volume_attachment.controller_volume_attachment.*.ipv4, [""]), 0) : "none"
  login_mount_ip = var.login_block ? element(concat(oci_core_volume_attachment.login_volume_attachment.*.ipv4, [""]), 0) : "none"

  scratch_nfs_type = var.cluster_network ? var.scratch_nfs_type_cluster : var.scratch_nfs_type_pool 

  iscsi_ip = var.cluster_network ? element(concat(oci_core_volume_attachment.cluster_network_volume_attachment.*.ipv4, [""]), 0) : element(concat(oci_core_volume_attachment.instance_pool_volume_attachment.*.ipv4, [""]), 0)

  mount_ip = local.scratch_nfs_type == "block" ? local.iscsi_ip : "none" 

// Cluster OCID


  cluster_ocid = var.node_count > 0 ? var.compute_cluster ? oci_core_compute_cluster.compute_cluster[0].id : var.cluster_network ? oci_core_cluster_network.cluster_network[0].id : oci_core_instance_pool.instance_pool[0].id : ""
  host = var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip[0].ip_address : oci_core_instance.controller.public_ip
  controller_bool_ip = var.private_deployment ? false : true
  login_bool_ip = var.private_deployment ? false : true
  controller_subnet = var.private_deployment ? oci_core_subnet.private-subnet : oci_core_subnet.public-subnet
  private_subnet_cidr = var.private_deployment ? [var.public_subnet, var.private_subnet] : [var.private_subnet]
  host_backup = var.slurm_ha ? var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip_backup[0].ip_address : oci_core_instance.backup[0].public_ip : "none"
  host_login = var.login_node ? var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip_login[0].ip_address : oci_core_instance.login[0].public_ip : "none"

  timeout_per_batch= var.cluster_network ? 30 : 15
  timeout_ip = join("",[ (( var.node_count - ( var.node_count % 20 ) )/20 + 1 ) * local.timeout_per_batch,"m"])

}
