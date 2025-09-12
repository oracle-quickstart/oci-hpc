setting to v.7.17 due to a bug in 7.18 for FSS sept.12 2025
provider "oci" {
auth = "InstancePrincipal"
region           = "${var.region}"
version = "7.17.0" 
}

# provider for home region for auth token provisioning
provider "oci" {
  alias  = "home"
  auth = "InstancePrincipal"
  region = var.home_region
}