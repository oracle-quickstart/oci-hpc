module "network" { 
	source			= "modules/network"
	compartment_ocid 	= "${var.compartment_ocid}"
	cidr_block		= "${var.network_cidr}"
	cluster_name		= "${local.cluster_name}" // optional. default: cluster
}
