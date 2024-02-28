locals {
//  listing_number = split(".", var.marketplace_listing)[0]
    mp_listing_id = var.use_marketplace_image ? substr(var.marketplace_listing,0,3) == "HPC" ? var.marketplace_listing_id_HPC : var.marketplace_listing_id_GPU : ""
    mp_controller_listing_id = var.use_marketplace_image_controller ?  substr(var.marketplace_listing_controller,0,3) == "HPC" ? var.marketplace_listing_id_HPC : var.marketplace_listing_id_GPU : ""
    mp_login_listing_id = var.use_marketplace_image_login ? substr(var.marketplace_listing_login,0,3) == "HPC" ? var.marketplace_listing_id_HPC : var.marketplace_listing_id_GPU : ""
    mp_version_id = var.marketplace_version_id[var.marketplace_listing]
    mp_controller_version_id = var.marketplace_version_id[var.marketplace_listing_controller]
    mp_login_version_id = var.marketplace_version_id[var.marketplace_listing_login]
}

/* 
output "debug" {
  value = data.oci_core_app_catalog_listing_resource_versions.app_catalog_listing_resource_versions.app_catalog_listing_resource_versions[0].listing_resource_id
}
*/ 

/*
data "oci_core_app_catalog_listing" "app_catalog_listing" {
    count = var.use_marketplace_image ? 1 : 0
    listing_id = local.mp_listing_id
}
*/ 
data "oci_core_app_catalog_listing_resource_versions" "app_catalog_listing_resource_versions" {
    count = var.use_marketplace_image ? 1 : 0
    listing_id = local.mp_listing_id
}

resource "oci_core_app_catalog_listing_resource_version_agreement" "mp_image_agreement" {
  count = var.use_marketplace_image ? 1 : 0

  listing_id               = local.mp_listing_id
  listing_resource_version = local.mp_version_id

}

resource "oci_core_app_catalog_subscription" "mp_image_subscription" {
  count                    = var.use_marketplace_image ? 1 : 0
  compartment_id           = var.targetCompartment
  eula_link                = oci_core_app_catalog_listing_resource_version_agreement.mp_image_agreement[0].eula_link
  listing_id               = oci_core_app_catalog_listing_resource_version_agreement.mp_image_agreement[0].listing_id
  listing_resource_version = oci_core_app_catalog_listing_resource_version_agreement.mp_image_agreement[0].listing_resource_version
  oracle_terms_of_use_link = oci_core_app_catalog_listing_resource_version_agreement.mp_image_agreement[0].oracle_terms_of_use_link
  signature                = oci_core_app_catalog_listing_resource_version_agreement.mp_image_agreement[0].signature
  time_retrieved           = oci_core_app_catalog_listing_resource_version_agreement.mp_image_agreement[0].time_retrieved

  timeouts {
    create = "20m"
  }
}

data "oci_core_app_catalog_listing_resource_versions" "controller_app_catalog_listing_resource_versions" {
    count = var.use_marketplace_image_controller ? 1 : 0
    listing_id = local.mp_controller_listing_id
}

resource "oci_core_app_catalog_listing_resource_version_agreement" "controller_mp_image_agreement" {
  count = ( var.use_marketplace_image_controller ) ? 1 : 0

  listing_id               = local.mp_controller_listing_id
  listing_resource_version = local.mp_controller_version_id

}

resource "oci_core_app_catalog_subscription" "controller_mp_image_subscription" {
  count                    = ( var.use_marketplace_image_controller ) ? 1 : 0
  compartment_id           = var.targetCompartment
  eula_link                = oci_core_app_catalog_listing_resource_version_agreement.controller_mp_image_agreement[0].eula_link
  listing_id               = oci_core_app_catalog_listing_resource_version_agreement.controller_mp_image_agreement[0].listing_id
  listing_resource_version = oci_core_app_catalog_listing_resource_version_agreement.controller_mp_image_agreement[0].listing_resource_version
  oracle_terms_of_use_link = oci_core_app_catalog_listing_resource_version_agreement.controller_mp_image_agreement[0].oracle_terms_of_use_link
  signature                = oci_core_app_catalog_listing_resource_version_agreement.controller_mp_image_agreement[0].signature
  time_retrieved           = oci_core_app_catalog_listing_resource_version_agreement.controller_mp_image_agreement[0].time_retrieved

  timeouts {
    create = "20m"
  }
}

data "oci_core_app_catalog_listing_resource_versions" "login_app_catalog_listing_resource_versions" {
    count = var.login_node && var.use_marketplace_image_login  ? 1 : 0
    listing_id = local.mp_login_listing_id
}

resource "oci_core_app_catalog_listing_resource_version_agreement" "login_mp_image_agreement" {
  count = var.login_node && var.use_marketplace_image_login ? 1 : 0

  listing_id               = local.mp_login_listing_id
  listing_resource_version = local.mp_login_version_id

}

resource "oci_core_app_catalog_subscription" "login_mp_image_subscription" {
  count                    = var.login_node && var.use_marketplace_image_login  ? 1 : 0
  compartment_id           = var.targetCompartment
  eula_link                = oci_core_app_catalog_listing_resource_version_agreement.login_mp_image_agreement[0].eula_link
  listing_id               = oci_core_app_catalog_listing_resource_version_agreement.login_mp_image_agreement[0].listing_id
  listing_resource_version = oci_core_app_catalog_listing_resource_version_agreement.login_mp_image_agreement[0].listing_resource_version
  oracle_terms_of_use_link = oci_core_app_catalog_listing_resource_version_agreement.login_mp_image_agreement[0].oracle_terms_of_use_link
  signature                = oci_core_app_catalog_listing_resource_version_agreement.login_mp_image_agreement[0].signature
  time_retrieved           = oci_core_app_catalog_listing_resource_version_agreement.login_mp_image_agreement[0].time_retrieved

  timeouts {
    create = "20m"
  }
}
