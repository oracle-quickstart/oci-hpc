
resource "oci_core_instance" "login" {
  count               = var.login_node ? 1 : 0
  depends_on          = [oci_core_subnet.public-subnet, null_resource.controller]
  availability_domain = var.login_ad
  compartment_id      = var.targetCompartment
  shape               = var.login_shape

  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }

  dynamic "shape_config" {
    for_each = local.is_login_flex_shape
    content {
      ocpus         = shape_config.value
      memory_in_gbs = var.login_custom_memory ? var.login_memory : 16 * shape_config.value
    }
  }
  agent_config {
    is_management_disabled = true
  }
  display_name = "${local.cluster_name}-login"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = oci_core_instance.controller.display_name
    "login"           = "true"
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
    user_data           = base64encode(file("cloud-init.sh"))
  }
  source_details {
    //    source_id   = var.use_standard_image ? data.oci_core_images.linux.images.0.id : local.custom_controller_image_ocid
    // source_id               = local.login_image
    source_id               = local.controller_image
    boot_volume_size_in_gbs = var.login_boot_volume_size
    boot_volume_vpus_per_gb = 30
    source_type             = "image"
  }

  create_vnic_details {
    subnet_id        = local.controller_subnet_id
    assign_public_ip = local.login_bool_ip
  }
}

resource "oci_dns_rrset" "rrset-login" {
  count           = var.login_node ? 1 : 0
  zone_name_or_id = data.oci_dns_zones.dns_zones.zones[0].id
  domain          = "${var.login_node ? oci_core_instance.login[0].display_name : ""}.${local.zone_name}"
  rtype           = "A"
  items {
    domain = "${var.login_node ? oci_core_instance.login[0].display_name : ""}.${local.zone_name}"
    rtype  = "A"
    rdata  = var.login_node ? oci_core_instance.login[0].private_ip : ""
    ttl    = 3600
  }
  view_id = data.oci_dns_views.dns_views.views[0].id
}
