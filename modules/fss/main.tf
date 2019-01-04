resource "oci_file_storage_file_system" "fss" {
  #Required
  availability_domain = "${lookup(data.oci_identity_availability_domains.ad.availability_domains[var.ad - 1],"name")}"
  compartment_id      = "${var.compartment_ocid}"
  #Optional
  display_name = "fss-${var.cluster_name}"
}


resource "oci_file_storage_export" "fss_export" {
  #Required
  export_set_id  = "${oci_file_storage_export_set.fss_exportset.id}"
  file_system_id = "${oci_file_storage_file_system.fss.id}"
  path           = "/${var.share_name}"

    export_options { 
    source = "${var.vcn_cidr}"
    access = "READ_WRITE"
    identity_squash = "NONE"
    require_privileged_source_port = false
    anonymous_gid = 65534
    anonymous_uid = 65534
  }
}

resource "oci_file_storage_export_set" "fss_exportset" {
  # Required
  mount_target_id = "${oci_file_storage_mount_target.fss_mt.id}"
  max_fs_stat_bytes = 23843202333
  max_fs_stat_files = 223442
}

resource "oci_file_storage_mount_target" "fss_mt" {
  #Required
  availability_domain = "${lookup(data.oci_identity_availability_domains.ad.availability_domains[var.ad - 1],"name")}"
  compartment_id      = "${var.compartment_ocid}"
  subnet_id           = "${var.subnet_id}"

  #Optional
  display_name = "fss-mt-${var.cluster_name}"
}

data "oci_core_private_ips" "fss_mt_ip" {
  subnet_id = "${oci_file_storage_mount_target.fss_mt.subnet_id}"

  filter {
    name   = "id"
    values = ["${oci_file_storage_mount_target.fss_mt.private_ip_ids.0}"]
  }
}

locals {
  mount_target_ip_address = "${lookup(data.oci_core_private_ips.fss_mt_ip.private_ips[0], "ip_address")}"
}

