data "oci_core_cluster_network_instances" "cluster_network_instances" {
  cluster_network_id = oci_core_cluster_network.cluster_network.id
  compartment_id     = var.compartment_ocid
}

data "oci_core_instance" "cluster_instances" {
  count       = var.node_count
  instance_id = data.oci_core_cluster_network_instances.cluster_network_instances.instances[count.index]["id"]
}

data "oci_core_subnet" "private_subnet" { 
  subnet_id = local.subnet_id 
}

data "oci_core_subnet" "public_subnet" { 
  subnet_id = local.bastion_subnet_id
} 
 
output "bastion" {
  value = oci_core_instance.bastion.public_ip
}

output "private_ips" {
  value = join(" ", data.oci_core_instance.cluster_instances.*.private_ip)
}

