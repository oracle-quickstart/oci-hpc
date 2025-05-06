resource "oci_lustre_file_storage_lustre_file_system" "lustre_file_system" {
  #Required
  count               = var.create_lfs ? 1 : 0
  availability_domain = var.ad
  capacity_in_gbs     = var.lfs_capacity_in_gbs
  compartment_id      = var.lfs_compartment
  file_system_name    = var.lfs_source_path # Mount name
  performance_tier    = var.lfs_perf_tier

  root_squash_configuration {

    # #Optional
    # client_exceptions = var.lfs_root_squash_configuration_client_exceptions
    identity_squash = "NONE"
    # squash_gid = var.lfs_root_squash_configuration_squash_gid
    # squash_uid = var.lfs_root_squash_configuration_squash_uid
  }
  subnet_id = local.subnet_id

  #Optional
  # cluster_placement_group_id = oci_cluster_placement_groups_cluster_placement_group.test_cluster_placement_group.id
  # defined_tags = {"Operations.CostCenter"= "42"}
  display_name            = "${local.cluster_name}-lfs"            	# File system name
  #file_system_description = var.lfs_file_system_description # File system description Optional
  freeform_tags = {
    "lfs_cluster_name"   = local.cluster_name
  }
  # kms_key_id = oci_kms_key.test_key.id
  # nsg_ids = var.lustre_file_system_nsg_ids
}
