resource "oci_core_volume" "volume" { 
        count                   = "${var.volumes * var.instances}"
        compartment_id          = "${var.compartment_ocid}"
        availability_domain     = "${lookup(data.oci_identity_availability_domains.ad.availability_domains[var.ad - 1], "name")}"
        display_name            = "${var.name}-volume-${count.index}-${var.cluster_name}"
	    size_in_gbs 		    = "${var.volume_size}"
}

resource "oci_core_volume_attachment" "attachment" { 
    count                   = "${var.volumes * var.instances}"
	attachment_type		    = "${var.attachment_type}"
	instance_id 		    = "${oci_core_instance.instance.*.id[count.index / var.volumes]}"
	volume_id		        = "${oci_core_volume.volume.*.id[count.index]}"
}

resource "oci_core_instance" "instance" { 
    count                   = "${var.instances}"
	compartment_id 		    = "${var.compartment_ocid}"
	availability_domain 	= "${lookup(data.oci_identity_availability_domains.ad.availability_domains[var.ad - 1], "name")}"
	display_name 		    = "${var.name}-${count.index + 1}-${var.cluster_name}"
	shape			        = "${var.shape}"
	
	create_vnic_details {	
		subnet_id 		    = "${var.subnet_id}"
		assign_public_ip 	= "${var.public_ip}"
	} 
	metadata {
        ssh_authorized_keys = "${var.ssh_key}"
        user_data           = "${base64encode(var.bootstrap)}"
	}
	source_details {
		source_type 		= "${var.source_type}"
		source_id 		    = "${var.source_id}"
	}
}