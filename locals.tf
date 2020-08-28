locals { 
// display names of instances 
  cluster_instances_names = var.cluster_network ? data.oci_core_instance.cluster_network_instances[0].*.display_name : data.oci_core_instance.instance_pool_instances[0].*.display_name

// ips of the instances
  cluster_instances_ips = var.cluster_network ? data.oci_core_instance.cluster_network_instances[0].*.private_ip : data.oci_core_instance.instance_pool_instances[0].*.private_ip

// subnet id derived either from created subnet or existing if specified
  subnet_id = var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0)

// subnet id derived either from created subnet or existing if specified
  bastion_subnet_id = var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.public-subnet.*.id, [""]), 0)

  cluster_name = var.use_custom_name ? var.cluster_name : random_pet.name.id
}


