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

output "grafana_password" {
  value     = random_password.grafana_admin_pwd.result
  sensitive = true
}

output "grafana_url" {
  value = var.cluster_monitoring ? (
    var.monitoring_node ? (
      oci_core_instance.monitoring[0].public_ip != "" ?  "https://grafana.${oci_core_instance.monitoring[0].public_ip}.${var.wildcard_dns_domain}" : "http://${oci_core_instance.monitoring[0].private_ip}"
    ) : (
      oci_core_instance.controller.public_ip != "" ?  "https://grafana.${oci_core_instance.controller.public_ip}.${var.wildcard_dns_domain}" : "http://${oci_core_instance.controller.private_ip}"
    )
  ) : "N/A"
}