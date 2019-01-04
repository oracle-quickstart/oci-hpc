resource "oci_core_vcn" "vcn" { 
	cidr_block	= "${var.cidr_block}"
	compartment_id	= "${var.compartment_ocid}"
	display_name	= "vcn-${var.cluster_name}"
	dns_label	= "${var.cluster_name}"
	} 


resource "oci_core_internet_gateway" "ig1" {
	compartment_id = "${var.compartment_ocid}"
	display_name   = "ig-${var.cluster_name}"
	vcn_id         = "${oci_core_vcn.vcn.id}"
}

resource "oci_core_nat_gateway" "ng1" {
	compartment_id = "${var.compartment_ocid}"
	vcn_id         = "${oci_core_vcn.vcn.id}"
	display_name   = "ng-${var.cluster_name}"
}

resource "oci_core_default_route_table" "default-route-table" {
	manage_default_resource_id = "${oci_core_vcn.vcn.default_route_table_id}"
	display_name               = "default-route-table-${var.cluster_name}"

	route_rules {
		destination       = "0.0.0.0/0"
		destination_type  = "CIDR_BLOCK"
		network_entity_id = "${oci_core_internet_gateway.ig1.id}"
	}
}

resource "oci_core_route_table" "private-route-table" {
	compartment_id = "${var.compartment_ocid}"
	vcn_id         = "${oci_core_vcn.vcn.id}"
	display_name   = "private-route-table-${var.cluster_name}"

	route_rules {
		destination       = "0.0.0.0/0"
		destination_type  = "CIDR_BLOCK"
		network_entity_id = "${oci_core_nat_gateway.ng1.id}"
	}
}

resource "oci_core_default_security_list" "default-security-list" {
	manage_default_resource_id = "${oci_core_vcn.vcn.default_security_list_id}"
	display_name               = "default-security-list-${var.cluster_name}"

  	// allow outbound tcp traffic on all ports
  	egress_security_rules {
    		destination = "0.0.0.0/0"
    		protocol    = "6"
  	}

  	ingress_security_rules {
    		protocol  = 1
    		source    = "0.0.0.0/0"
    		stateless = true

		icmp_options {
		      "type" = 3
		      "code" = 4
		}
	}
}

resource "oci_core_security_list" "custom-security-list" {
	display_name	= "public-security-list-${var.cluster_name}"
	compartment_id	= "${var.compartment_ocid}"	
	vcn_id		= "${oci_core_vcn.vcn.id}"
	
	ingress_security_rules {
		protocol	= "all" 
		source		= "${oci_core_vcn.vcn.cidr_block}"
		stateless 	= true
	} 

	ingress_security_rules { 
		protocol 	= 6
		source		= "0.0.0.0/0"
		tcp_options { 
			"min"	= "22"
			"max"	= "22"
		}
	}
}

resource "oci_core_subnet" "public-subnet-1" { 
    count               = "${length(data.oci_identity_availability_domains.ad.availability_domains)}"
	display_name	    = "public-sn-${count.index + 1}-${var.cluster_name}"
	cidr_block	        = "${cidrsubnet(oci_core_vcn.vcn.cidr_block, 8, count.index)}"
	compartment_id	    = "${var.compartment_ocid}"
	vcn_id		        = "${oci_core_vcn.vcn.id}"
	route_table_id	    = "${oci_core_default_route_table.default-route-table.id}"
	security_list_ids   = ["${oci_core_default_security_list.default-security-list.id}", "${oci_core_security_list.custom-security-list.id}"]
	availability_domain = "${lookup(data.oci_identity_availability_domains.ad.availability_domains[count.index],"name")}"
	dns_label	        = "ad${count.index + 1}pub1"
}

resource "oci_core_subnet" "private-subnet-1" {
    count               = "${length(data.oci_identity_availability_domains.ad.availability_domains)}"
    display_name        = "private-sn-${count.index + 1}-${var.cluster_name}"
    cidr_block          = "${cidrsubnet(oci_core_vcn.vcn.cidr_block, 8, length(data.oci_identity_availability_domains.ad.availability_domains) + count.index)}"
    compartment_id      = "${var.compartment_ocid}"
    vcn_id              = "${oci_core_vcn.vcn.id}"
    route_table_id      = "${oci_core_route_table.private-route-table.id}"
    security_list_ids   = ["${oci_core_default_security_list.default-security-list.id}", "${oci_core_security_list.custom-security-list.id}"]
    availability_domain = "${lookup(data.oci_identity_availability_domains.ad.availability_domains[count.index],"name")}"
	dns_label	        = "ad${count.index + 1}priv1"
}
