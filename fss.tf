module "fss" { 
  source            = "modules/fss"
  compartment_ocid  = "${var.compartment_ocid}"
  subnet_id         = "${element(module.network.public-subnet-1-id, var.ad - 1)}" // required
  vcn_cidr          = "${module.network.vcn-cidr}"
  ad                = "${var.ad}"
  cluster_name      = "${local.cluster_name}"
  share_name        = "${local.fss_share_name}"
}