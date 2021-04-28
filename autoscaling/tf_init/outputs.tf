output "private_ips" {
  value = join(",", local.cluster_instances_ips)
}
output "hostnames" {
  value = join(",", local.cluster_instances_names)
}
output "ocids" {
  value = join(",", local.cluster_instances_ids)
}
output "cluster_ocid" {
  value = oci_core_cluster_network.cluster_network[0].id
}

