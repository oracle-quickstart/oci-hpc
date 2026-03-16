#provider "oci" {
#tenancy_ocid     = "${var.tenancy_ocid}"
#user_ocid        = "${var.user_ocid}"
#fingerprint      = "${var.fingerprint}"
#private_key_path = "${var.private_key_path}"
#region           = "${var.region}"
#}

# provider for home region for auth token provisioning
provider "oci" {
  alias  = "home"
  region = var.home_region
}