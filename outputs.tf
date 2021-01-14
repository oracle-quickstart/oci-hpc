output "bastion" {
  value = oci_core_instance.bastion.public_ip
}

output "private_ips" {
  value = join(" ", local.cluster_instances_ips)
}

