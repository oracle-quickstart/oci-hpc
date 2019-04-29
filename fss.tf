module "fss" { 
  source            = "modules/fss"
  compartment_ocid  = "${var.compartment_ocid}"
  subnet_id         = "${module.network.private-subnet-1-id}" // required
  vcn_cidr          = "${module.network.vcn-cidr}"
  ad                = "${var.ad}"
  cluster_name      = "${local.cluster_name}"
  share_name        = "${local.fss_share_name}"
}
