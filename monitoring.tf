resource "oci_core_instance" "monitoring" {
  count = var.monitoring_node ? 1 : 0
  depends_on          = [oci_core_subnet.public-subnet]
  availability_domain = var.monitoring_ad
  compartment_id      = var.targetCompartment
  shape               = var.monitoring_shape

  dynamic "shape_config" {
    for_each = local.is_monitoring_flex_shape
      content {
        ocpus = shape_config.value
        memory_in_gbs = var.monitoring_custom_memory ? var.monitoring_memory : 16 * shape_config.value
      }
  }
  agent_config {
    is_management_disabled = true
    }
  display_name        = "${local.cluster_name}-monitoring"

  freeform_tags = {
    "cluster_name" = local.cluster_name
    "parent_cluster" = local.cluster_name
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
    user_data           = base64encode(data.template_file.controller_config.rendered)
  }
  source_details {
    source_id = local.monitoring_image
    boot_volume_size_in_gbs = var.monitoring_boot_volume_size
    boot_volume_vpus_per_gb = 30
    source_type = "image"
  }

  create_vnic_details {
    subnet_id = local.controller_subnet_id
    assign_public_ip = local.monitoring_bool_ip
  }
} 

resource "oci_dns_rrset" "rrset-monitoring" {
  count = var.monitoring_node && var.dns_entries ? 1 : 0
  zone_name_or_id = data.oci_dns_zones.dns_zones.zones[0].id
  domain          = "${var.monitoring_node ? oci_core_instance.monitoring[0].display_name : ""}.${local.zone_name}"
  rtype           = "A"
  items {
    domain = "${var.monitoring_node ? oci_core_instance.monitoring[0].display_name : ""}.${local.zone_name}"
    rtype  = "A"
    rdata  = var.monitoring_node ? oci_core_instance.monitoring[0].private_ip: ""
    ttl    = 3600
  }
  scope = "PRIVATE"
  view_id = data.oci_dns_views.dns_views.views[0].id
}