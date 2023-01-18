resource "oci_core_volume" "login_volume" { 
  count = var.login_block && var.login_node ? 1 : 0
  availability_domain = var.login_ad
  compartment_id = var.targetCompartment
  display_name = "${local.cluster_name}-login"
  size_in_gbs = var.login_block_volume_size
  vpus_per_gb = split(".", var.login_block_volume_performance)[0]
} 


resource "oci_core_volume_attachment" "login_volume_attachment" { 
  count = var.login_block && var.login_node ? 1 : 0
  attachment_type = "iscsi"
  volume_id       = oci_core_volume.login_volume[0].id
  instance_id     = oci_core_instance.login[0].id
  display_name    = "${local.cluster_name}-login-volume-attachment"
  device          = "/dev/oracleoci/oraclevdb"
} 

resource "oci_core_instance" "login" {
  count = var.login_node ? 1 : 0
  depends_on          = [oci_core_subnet.public-subnet]
  availability_domain = var.login_ad
  compartment_id      = var.targetCompartment
  shape               = var.login_shape

  dynamic "shape_config" {
    for_each = local.is_login_flex_shape
      content {
        ocpus = shape_config.value
        memory_in_gbs = var.login_custom_memory ? var.login_memory : 16 * shape_config.value
      }
  }
  agent_config {
    is_management_disabled = true
    }
  display_name        = "${local.cluster_name}-login"

  freeform_tags = {
    "cluster_name" = local.cluster_name
    "parent_cluster" = local.cluster_name
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
    user_data           = base64encode(data.template_file.bastion_config.rendered)
  }
  source_details {
//    source_id   = var.use_standard_image ? data.oci_core_images.linux.images.0.id : local.custom_bastion_image_ocid
    source_id = local.login_image
    boot_volume_size_in_gbs = var.login_boot_volume_size
    source_type = "image"
  }

  create_vnic_details {
    subnet_id = local.bastion_subnet_id
    assign_public_ip = local.login_bool_ip
  }
} 
