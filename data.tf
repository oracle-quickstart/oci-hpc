resource "random_pet" "name" {
  length = 2
}

resource "tls_private_key" "ssh" {
  algorithm = "ED25519"
}

data "oci_core_services" "services" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}
data "oci_core_cluster_network_instances" "cluster_network_instances" {
  count              = (!var.compute_cluster) && var.cluster_network && var.node_count > 0 ? 1 : 0
  cluster_network_id = oci_core_cluster_network.cluster_network[0].id
  compartment_id     = var.targetCompartment
}

data "oci_core_instance_pool_instances" "instance_pool_instances" {
  count            = (!var.cluster_network) && (var.node_count > 0) ? 1 : 0
  instance_pool_id = oci_core_instance_pool.instance_pool[0].id
  compartment_id   = var.targetCompartment
}

data "oci_core_instance" "cluster_network_instances" {
  count       = (!var.compute_cluster) && var.cluster_network && var.node_count > 0 ? var.node_count : 0
  instance_id = data.oci_core_cluster_network_instances.cluster_network_instances[0].instances[count.index]["id"]
}

data "oci_core_instance" "instance_pool_instances" {
  count       = var.cluster_network || var.node_count == 0 ? 0 : var.node_count
  instance_id = data.oci_core_instance_pool_instances.instance_pool_instances[0].instances[count.index]["id"]
}

data "oci_core_vcn" "vcn" {
  vcn_id = local.vcn_id
}
data "oci_core_subnet" "private_subnet" {
  subnet_id = local.subnet_id
}

data "oci_core_subnet" "public_subnet" {
  subnet_id = local.controller_subnet_id
}

data "oci_resourcemanager_private_endpoint_reachable_ip" "private_endpoint_reachable_ip" {
  #Required
  count               = var.private_deployment ? 1 : 0
  private_endpoint_id = oci_resourcemanager_private_endpoint.rms_private_endpoint[0].id
  private_ip          = tostring(oci_core_instance.controller.private_ip)
}

data "oci_resourcemanager_private_endpoint_reachable_ip" "private_endpoint_reachable_ip_backup" {
  #Required
  count               = (var.private_deployment && var.slurm_ha) ? 1 : 0
  private_endpoint_id = oci_resourcemanager_private_endpoint.rms_private_endpoint[0].id
  private_ip          = tostring(oci_core_instance.backup[0].private_ip)
}

data "oci_resourcemanager_private_endpoint_reachable_ip" "private_endpoint_reachable_ip_login" {
  #Required
  count               = (var.private_deployment && var.login_node) ? 1 : 0
  private_endpoint_id = oci_resourcemanager_private_endpoint.rms_private_endpoint[0].id
  private_ip          = tostring(oci_core_instance.login[0].private_ip)
}

data "oci_resourcemanager_private_endpoint_reachable_ip" "private_endpoint_reachable_ip_monitoring" {
  #Required
  count               = (var.private_deployment && var.monitoring_node) ? 1 : 0
  private_endpoint_id = oci_resourcemanager_private_endpoint.rms_private_endpoint[0].id
  private_ip          = tostring(oci_core_instance.monitoring[0].private_ip)
}

data "oci_dns_views" "dns_views" {
  depends_on     = [local.controller_subnet, oci_core_vcn.vcn]
  compartment_id = var.vcn_compartment
  scope          = "PRIVATE"
  display_name   = data.oci_core_vcn.vcn.display_name
}

data "oci_dns_zones" "dns_zones" {
  depends_on     = [local.controller_subnet, oci_core_vcn.vcn, oci_dns_zone.dns_zone]
  compartment_id = var.vcn_compartment
  name           = local.zone_name
  zone_type      = "PRIMARY"
  scope          = "PRIVATE"
}