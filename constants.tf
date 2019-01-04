variable "tenancy_ocid" {}
variable "user_ocid" {}
variable "fingerprint" {}
variable "private_key_path" {}
variable "region" {}
variable "compartment_ocid" {}
variable "gluster_role" { default = "gluster" }
variable "gluster_name" { default = "gluster" }
variable "headnode_role" { default = "master" }
variable "headnode_name" { default = "headnode" }
variable "compute_role" { default = "compute" }
variable "compute_name" { default = "compute" }
variable "fss_share_name" { default = "share" } 

provider "oci" {
  tenancy_ocid     = "${var.tenancy_ocid}"
  user_ocid        = "${var.user_ocid}"
  fingerprint      = "${var.fingerprint}"
  private_key_path = "${var.private_key_path}"
  region           = "${var.region}"
}
