locals {
  master_address = "headnode-1-${local.cluster_name}.${module.network.public-subnet-1-dns}.${module.network.vcn-dns}.oraclevcn.com"
}


data "oci_identity_availability_domains" "ad" { 
	compartment_id = "${var.compartment_ocid}"
} 

data "template_file" "master_template" { 
	template = "${file("${path.module}/conf/master.tpl")}"
	vars {
		master_address = "${local.master_address}"
		ssh_key = "${base64encode(tls_private_key.key.private_key_pem)}"
		par_url = "${local.par_url}"
		role	= "${jsonencode(concat(local.headnode_role, var.additional_headnode_roles, var.additional_role_all))}"

	}
}
data "template_file" "salt_variables" { 
	template = "${file("${path.module}/conf/variables.tpl")}"
	vars { 
		cluster_name = "${local.cluster_name}"
		fss_ip = "${module.fss.mt_ip}"
		vcn_cidr = "${module.network.vcn-cidr}"
		fss_share_name = "${local.fss_share_name}"
		storage_servers = "${join(",", module.storage.instance_name)}"
		public_subnet_name = "${module.network.public-subnet-1-dns}"
		private_subnet_name = "${module.network.private-subnet-1-dns}"
		storage_type	= "${var.storage_type}"
	}
}

resource "local_file" "salt_variables" { 
	filename = "${path.module}/salt/pillar/variables.sls"
	content = "${data.template_file.salt_variables.rendered}"
}

resource "local_file" "key_sls" { 
	filename = "${path.module}/salt/salt/id_rsa" 
	content = "${tls_private_key.key.private_key_pem}"
} 

data "template_file" "worker_template" { 
	template = "${file("${path.module}/conf/worker.tpl")}"
	vars { 
		master_address = "${local.master_address}"
		role	= "${jsonencode(concat(local.compute_role, var.additional_worker_roles, var.additional_role_all))}"
	}
}

data "template_file" "storage_template" { 
	template = "${file("${path.module}/conf/storage.tpl")}"
	vars { 
		master_address = "${local.master_address}"
role	= "${jsonencode(concat(local.storage_role, var.additional_storage_roles, var.additional_role_all))}"	}
}

data "template_file" "gpu_template" { 
	template = "${file("${path.module}/conf/gpu.tpl")}"
	vars { 
		master_address = "${local.master_address}"
role	= "${jsonencode(concat(local.gpu_role, var.additional_gpu_roles, var.additional_role_all))}"	}
}


resource "random_pet" "server" {
    length = 2
    separator = ""
}

locals { 
    cluster_name = "${substr(random_pet.server.id, 0, min(15, length(random_pet.server.id)))}"
}

