resource "random_pet" "name" {
  length = 2
}

locals {
  cluster_name = random_pet.name.id
}

resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = "4096"
}

resource "oci_core_vcn" "vcn" {
  count          = var.use_existing_vcn ? 0 : 1
  cidr_block     = var.vcn_subnet
  compartment_id = var.compartment_ocid
  display_name   = "${local.cluster_name}_VCN"
  dns_label      = "cluster"
}

resource "oci_core_security_list" "internal-security-list" {
  count          = var.use_existing_vcn ? 0 : 1
  vcn_id         = oci_core_vcn.vcn[0].id
  compartment_id = var.compartment_ocid

  ingress_security_rules {
    protocol = "all"
    source   = var.vcn_subnet
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_internet_gateway" "ig1" {
  count          = var.use_existing_vcn ? 0 : 1
  vcn_id         = oci_core_vcn.vcn[0].id
  compartment_id = var.compartment_ocid
  display_name   = "${local.cluster_name}_internet-gateway"
}

resource "oci_core_nat_gateway" "ng1" {
  count          = var.use_existing_vcn ? 0 : 1
  vcn_id         = oci_core_vcn.vcn[0].id
  compartment_id = var.compartment_ocid
  display_name   = "${local.cluster_name}_nat-gateway"
}

resource "oci_core_route_table" "public_route_table" {
  count          = var.use_existing_vcn ? 0 : 1
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.vcn[0].id
  display_name   = "${local.cluster_name}_public_route_table"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.ig1[0].id
  }
}

resource "oci_core_route_table" "private_route_table" {
  count          = var.use_existing_vcn ? 0 : 1
  display_name   = "${local.cluster_name}_private_route_table"
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.vcn[0].id

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.ng1[0].id
  }
}

resource "oci_core_subnet" "public-subnet" {
  count               = var.use_existing_vcn ? 0 : 1
  availability_domain = var.ad
  vcn_id              = oci_core_vcn.vcn[0].id
  compartment_id      = var.compartment_ocid
  cidr_block          = var.public_subnet
  security_list_ids   = [oci_core_vcn.vcn[0].default_security_list_id, oci_core_security_list.internal-security-list[0].id]
  dns_label           = "public"
  display_name        = "${local.cluster_name}_public_subnet"
  route_table_id      = oci_core_route_table.public_route_table[0].id
}

resource "oci_core_subnet" "private-subnet" {
  count                      = var.use_existing_vcn ? 0 : 1
  availability_domain        = var.ad
  vcn_id                     = oci_core_vcn.vcn[0].id
  compartment_id             = var.compartment_ocid
  cidr_block                 = var.private_subnet
  security_list_ids          = [oci_core_vcn.vcn[0].default_security_list_id, oci_core_security_list.internal-security-list[0].id]
  dns_label                  = "private"
  display_name               = "${local.cluster_name}_private_subnet"
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.private_route_table[0].id
}

