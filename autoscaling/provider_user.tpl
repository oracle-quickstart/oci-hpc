provider "oci" {
tenancy_ocid     = var.tenancy_ocid
user_ocid        = "${api_user_ocid}"
fingerprint      = "${api_fingerprint}"
private_key_path = "${private_key_path}"
region           = var.region
}

# provider for home region for auth token provisioning
provider "oci" {
  alias  = "home"
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = "${api_user_ocid}"
  fingerprint      = "${api_fingerprint}"
  private_key_path = "${private_key_path}"  
  region = var.home_region
}