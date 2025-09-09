provider "oci" {
auth = "InstancePrincipal"
region           = "${var.region}"
}

# provider for home region for auth token provisioning
provider "oci" {
  alias  = "home"
  auth = "InstancePrincipal"
  region = var.home_region
}