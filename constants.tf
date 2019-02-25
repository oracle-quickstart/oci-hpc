variable "tenancy_ocid" {}
variable "user_ocid" {}
variable "fingerprint" {}
variable "private_key_path" {}
variable "region" {}
variable "compartment_ocid" {}

locals { 
  storage_name = "storage"
  headnode_role = ["master"]
  headnode_name = "headnode"
  compute_role = ["compute"]
  compute_name = "compute"
  fss_share_name = "share"
  storage_role = ["storage"]
}

provider "oci" {
  tenancy_ocid     = "${var.tenancy_ocid}"
  user_ocid        = "${var.user_ocid}"
  fingerprint      = "${var.fingerprint}"
  private_key_path = "${var.private_key_path}"
  region           = "${var.region}"
}
