module "headnode" { 
        source          = "modules/instance"

        compartment_ocid  = "${var.compartment_ocid}"
        instances       = "1" // required
        subnet_id       = "${module.network.public-subnet-1-id}" // required
        ad              = "${var.ad}" // required
        name            = "${local.headnode_name}" // required
        ssh_key         = "${tls_private_key.key.public_key_openssh}" // required
        shape           = "${var.headnode_shape}" // required
        source_id       = "${lookup(var.image, var.region)}"

        // Optional parameters

        bootstrap       = "${data.template_file.master_template.rendered}"
        volumes         = "${var.headnode_volumes}" // optional. default: 0
        volume_size     = "${var.headnode_volume_size}" // optional. default: 50 
        source_type     = "image" // optional. default: image
        cluster_name    = "${local.cluster_name}" // optional. default: cluster
        public_ip       = true // optional. default: true
        
}

module "compute" { 
        
        source          = "modules/instance"
        compartment_ocid  = "${var.compartment_ocid}"
        instances       = "${var.compute_count}" // required
        subnet_id       = "${module.network.private-subnet-1-id}" // required
        ad              = "${var.ad}" // required
        name            = "${local.compute_name}" // required
        ssh_key         = "${tls_private_key.key.public_key_openssh}" // required
        shape           = "${var.compute_shape}" // required
        source_id       = "${lookup(var.image, var.region)}" // required

        // Optional parameters

        bootstrap       = "${data.template_file.worker_template.rendered}"
        volumes         = "${var.compute_volumes}" // optional. default: 0
        volume_size     = "${var.compute_volume_size}" // optional. default: 50 
        source_type     = "image" // optional. default: image
        cluster_name    = "${local.cluster_name}" // optional. default: cluster
        public_ip       = false // optional. default: true
        
}

module "storage" { 
        
        source          = "modules/instance"

        compartment_ocid  = "${var.compartment_ocid}"
        instances       = "${var.storage_count}" // required. can be 0 
        subnet_id       = "${module.network.private-subnet-1-id}" // required
        ad              = "${var.ad}" // required
        name            = "${local.storage_name}" // required
        ssh_key         = "${tls_private_key.key.public_key_openssh}" // required
        shape           = "${var.storage_shape}" // required
        source_id       = "${lookup(var.image, var.region)}" // required

        // Optional parameters
        
        bootstrap       = "${data.template_file.storage_template.rendered}"
        volumes         = "${var.storage_volumes}" // optional. default: 0
        volume_size     = "${var.storage_volume_size}" // optional. default: 50 
        source_type     = "image" // optional. default: image
        cluster_name    = "${local.cluster_name}" // optional. default: cluster
        public_ip       = false // optional. default: true
        
}