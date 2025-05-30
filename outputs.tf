output "controller" {
  value = local.host
}

output "private_ips" {
  value = join(" ", local.cluster_instances_ips)
}

output "backup" {
  value = var.slurm_ha ? local.host_backup : "No Slurm Backup Defined"
}

output "login" {
  value = var.login_node ? local.host_login : "No Login Node Defined"
}

output "monitoring" {
  value = var.monitoring_node ? local.host_monitoring : "No Monitoring Node Defined"
}

output "fabric" {
  value = join(
    ",",
    flatten([
      for fabric in data.oci_core_compute_gpu_memory_fabrics.test_compute_gpu_memory_fabrics.compute_gpu_memory_fabric_collection :
      [for item in fabric.items : item.id]
    ])
  )
}