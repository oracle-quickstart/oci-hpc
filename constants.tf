variable "tenancy_ocid" {}
variable "user_ocid" {}
variable "fingerprint" {}
variable "private_key_path" {}
variable "region" {}
variable "compartment_ocid" {}

locals { 
  storage_name 	 =   "storage"
  storage_role 	 =   ["storage"]
  headnode_name  =   "headnode"
  headnode_role  =   ["master"]
  compute_name 	 =   "compute"
  compute_role 	 =   ["compute"]
  gpu_name	 =   "gpu"
  gpu_role     	 =   ["gpu"]
  fss_share_name =   "share"
}

provider "oci" {
  tenancy_ocid     = "${var.tenancy_ocid}"
  user_ocid        = "${var.user_ocid}"
  fingerprint      = "${var.fingerprint}"
  private_key_path = "${var.private_key_path}"
  region           = "${var.region}"
}
