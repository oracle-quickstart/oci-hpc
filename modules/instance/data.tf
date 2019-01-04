data "oci_identity_availability_domains" "ad" { 
	compartment_id = "${var.compartment_ocid}"
} 

data "oci_core_subnet" "subnet" { 
    subnet_id = "${var.subnet_id}"
}