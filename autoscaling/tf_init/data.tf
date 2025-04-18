resource "random_pet" "name" {
  length = 2
}
data "oci_core_services" "services" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

data "oci_core_cluster_network_instances" "cluster_network_instances" {
  count = (! var.compute_cluster) && var.cluster_network && var.node_count > 0 ? 1 : 0
  cluster_network_id = oci_core_cluster_network.cluster_network[0].id
  compartment_id     = var.targetCompartment
}

data "oci_core_instance_pool_instances" "instance_pool_instances" {
  count = var.cluster_network || var.node_count == 0 ? 0 : 1
  instance_pool_id = oci_core_instance_pool.instance_pool[0].id
  compartment_id     = var.targetCompartment
}

data "oci_core_instance" "cluster_network_instances" {
  count       = (! var.compute_cluster) && var.cluster_network && var.node_count > 0 ? var.node_count : 0
  instance_id = data.oci_core_cluster_network_instances.cluster_network_instances[0].instances[count.index]["id"]
}

data "oci_core_instance" "instance_pool_instances" {
  count       = var.cluster_network || var.node_count == 0 ? 0 : var.node_count
  instance_id = data.oci_core_instance_pool_instances.instance_pool_instances[0].instances[count.index]["id"]
}

data "oci_core_subnet" "private_subnet" { 
  subnet_id = local.subnet_id 
}

data "oci_core_subnet" "public_subnet" { 
  subnet_id = local.controller_subnet_id
} 
 
data "oci_core_images" "linux" {
  compartment_id = var.targetCompartment
  operating_system = "Oracle Linux"
  operating_system_version = "7.8"
  filter {
    name = "display_name"
    values = ["^([a-zA-z]+)-([a-zA-z]+)-([\\.0-9]+)-([\\.0-9-]+)$"]
    regex = true
  }
}

data "oci_core_vcn" "vcn" { 
  vcn_id = local.vcn_id
} 

data "oci_dns_views" "dns_views" {
  compartment_id = var.vcn_compartment
  scope = "PRIVATE"
  display_name = data.oci_core_vcn.vcn.display_name
}

data "oci_dns_zones" "dns_zones" {
    compartment_id = var.vcn_compartment
    name = "${var.zone_name}"
    zone_type = "PRIMARY"
    scope = "PRIVATE"
}
