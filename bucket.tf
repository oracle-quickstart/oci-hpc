resource "oci_objectstorage_bucket" "cluster_bucket" {
  count          = var.create_bucket ? 1 : 0
  compartment_id = var.targetCompartment
  name           = "${local.cluster_name}-bucket"
  namespace      = local.ocir_namespace

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "oci_identity_customer_secret_key" "customer_secret_key" {
    count        = var.create_bucket ? 1 : 0
    display_name = "${local.cluster_name}-secret-key"
    user_id      = var.current_user_ocid
    provider     = oci.home
}
