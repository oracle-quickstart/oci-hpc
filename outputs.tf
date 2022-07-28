output "bastion" {
  value = local.host
}

output "private_ips" {
  value = join(" ", local.cluster_instances_ips)
}

output "backup" {
  value = var.slurm_ha ? local.host_backup : "No Slurm Backup Defined"
}