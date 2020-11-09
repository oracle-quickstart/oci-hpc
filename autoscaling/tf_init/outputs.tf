output "private_ips" {
  value = join(" ", local.cluster_instances_ips)
}

