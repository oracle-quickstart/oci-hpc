locals { 
  bastion_subnet_id = "${var.use_existing_vcn ? var.bastion_subnet_id : element(concat(oci_core_subnet.public-subnet.*.id, list("")), 0)}"
}

data "template_file" "bastion_config" {
        template = "${file("config.bastion")}"
        vars = { 
		key = "${tls_private_key.ssh.private_key_pem}"
	} 
}

resource "oci_core_instance" "bastion" {
    depends_on = ["oci_core_cluster_network.cluster_network"]
    availability_domain = "${var.ad}"
    compartment_id = "${var.compartment_ocid}"
    shape = "${var.bastion_shape}"
    display_name = "${local.cluster_name}-bastion"
    metadata = {
      ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
      user_data = "${base64encode(data.template_file.bastion_config.rendered)}"
    } 
    source_details {
        source_id = "${var.bastion_image[var.region]}"
        source_type = "image"
    } 
    create_vnic_details {
        subnet_id = "${local.bastion_subnet_id}"
    } 

    provisioner "file" {
    	content     = "${tls_private_key.ssh.private_key_pem}"
	destination = "/home/opc/.ssh/cluster.key"
	connection { 
		host = "${oci_core_instance.bastion.public_ip}"
		type = "ssh"
      		user = "opc" 
      		private_key = "${tls_private_key.ssh.private_key_pem}"
		}

	} 

    provisioner "file" {
    	content     = "${tls_private_key.ssh.private_key_pem}"
	destination = "/home/opc/.ssh/id_rsa"
	connection { 
		host = "${oci_core_instance.bastion.public_ip}"
		type = "ssh"
      		user = "opc" 
      		private_key = "${tls_private_key.ssh.private_key_pem}"
		}

	} 
    provisioner "file" {
        content     = "${join("\n", data.oci_core_instance.cluster_instances.*.private_ip)}"
        destination = "/tmp/hosts"
        connection {
                host = "${oci_core_instance.bastion.public_ip}"
                type = "ssh"
                user = "opc"
                private_key = "${tls_private_key.ssh.private_key_pem}"
                }

        }

    provisioner "file" {
	source = "configure.sh" 
	destination = "/tmp/configure.sh"
	connection { 
		host = "${oci_core_instance.bastion.public_ip}"
		type = "ssh"
      		user = "opc" 
      		private_key = "${tls_private_key.ssh.private_key_pem}"
		}

   } 

   provisioner "remote-exec" { 
   inline = [ 
     "chmod 600 /home/opc/.ssh/cluster.key",
     "chmod 600 /home/opc/.ssh/id_rsa",
     "chmod a+x /tmp/configure.sh", 
     "bash /tmp/configure.sh",
     "/opt/oci-hpc/setup/provision/HPC_PROVISION/hpc_provision_cluster_nodes.sh -i /home/opc/.ssh/cluster.key -p -b -f ${join(" ", data.oci_core_instance.cluster_instances.*.private_ip)}"
   ] 
   connection {
   	host = "${oci_core_instance.bastion.public_ip}"
        type = "ssh"
        user = "opc"
        private_key = "${tls_private_key.ssh.private_key_pem}"
        }
   }
}
