resource "oci_file_storage_file_system" "FSS" {
  count               = var.add_nfs && var.create_fss == "new" ? 1 : 0
  availability_domain = var.fss_ad
  compartment_id      = var.fss_compartment
  display_name        = "${local.cluster_name}-fss"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "oci_file_storage_file_system" "config_fss" {
  availability_domain = var.ad
  compartment_id      = var.targetCompartment
  display_name        = "${local.cluster_name}-config-fss"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "oci_file_storage_file_system" "FSS_home" {
  count               = var.add_nfs && var.create_fss == "new" && var.shared_home == "fss" ? 1 : 0
  availability_domain = var.fss_ad
  compartment_id      = var.fss_compartment
  display_name        = "${local.cluster_name}-fss-home"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "oci_file_storage_mount_target" "config_fss_mount_target" {
  availability_domain = var.ad
  compartment_id      = var.targetCompartment
  subnet_id           = local.subnet_id
  display_name        = "${local.cluster_name}-config-mt"
  hostname_label      = "configfs"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "oci_file_storage_mount_target" "FSSMountTarget" {
  count               = var.add_nfs && var.create_fss == "new" ? var.mount_target_count : 0
  availability_domain = var.fss_ad
  compartment_id      = var.fss_compartment
  subnet_id           = local.subnet_id
  display_name        = "${local.cluster_name}-mt-${count.index}"
  hostname_label      = "fileserver${count.index}"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "oci_file_storage_export" "config_fss_export" {
  export_set_id  = oci_file_storage_mount_target.config_fss_mount_target.export_set_id
  file_system_id = oci_file_storage_file_system.config_fss.id
  path           = "/config"
  export_options {
    source          = data.oci_core_vcn.vcn.cidr_block
    access          = "READ_WRITE"
    identity_squash = "NONE"
  }
}

resource "oci_file_storage_export" "FSSExport" {
  count          = var.add_nfs && var.create_fss == "new" ? (var.mount_target_count == 0 ? 1 : var.mount_target_count) : 0
  export_set_id  = var.mount_target_count == 0 ? oci_file_storage_mount_target.config_fss_mount_target.export_set_id : oci_file_storage_mount_target.FSSMountTarget[count.index].export_set_id
  file_system_id = oci_file_storage_file_system.FSS[0].id
  path           = var.nfs_source_path
  export_options {
    source          = data.oci_core_vcn.vcn.cidr_block
    access          = "READ_WRITE"
    identity_squash = "NONE"
  }
}

resource "oci_file_storage_export" "FSSExport_home" {
  count          = var.add_nfs && var.create_fss == "new" && var.shared_home == "fss" ? (var.mount_target_count == 0 ? 1 : var.mount_target_count) : 0
  export_set_id  = var.mount_target_count == 0 ? oci_file_storage_mount_target.config_fss_mount_target.export_set_id : oci_file_storage_mount_target.FSSMountTarget[count.index].export_set_id
  file_system_id = oci_file_storage_file_system.FSS_home[0].id
  path           = "/home"
  export_options {
    source          = data.oci_core_vcn.vcn.cidr_block
    access          = "READ_WRITE"
    identity_squash = "NONE"
  }
}

resource "null_resource" "fss_home_dependency" {
  triggers = {
    # This will only be set if FSS is created
    fss_export_home_id = var.add_nfs && var.create_fss == "new" && var.shared_home == "fss" ? oci_file_storage_export.FSSExport_home[0].id : ""
  }
}

resource "null_resource" "fss_config_dependency" {
  triggers = {
    config_fss_export_id = oci_file_storage_export.config_fss_export.id
  }
}
