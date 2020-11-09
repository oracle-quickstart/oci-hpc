resource "oci_core_volume" "bastion_volume" { 
  count = var.bastion_block ? 1 : 0
  availability_domain = var.bastion_ad
  compartment_id = var.targetCompartment
  display_name = "${local.cluster_name}-bastion-volume"
  
  size_in_gbs = var.bastion_block_volume_size
  vpus_per_gb = split(".", var.bastion_block_volume_performance)[0]
} 

resource "oci_core_volume_attachment" "bastion_volume_attachment" { 
  count = var.bastion_block ? 1 : 0 
  attachment_type = "iscsi"
  volume_id       = oci_core_volume.bastion_volume[0].id
  instance_id     = oci_core_instance.bastion.id
  display_name    = "${local.cluster_name}-bastion-volume-attachment"
  device          = "/dev/oracleoci/oraclevdb"
} 

resource "oci_core_instance" "bastion" {
  depends_on          = [oci_core_subnet.public-subnet]
  availability_domain = var.bastion_ad
  compartment_id      = var.targetCompartment
  shape               = var.bastion_shape

  dynamic "shape_config" {
    for_each = local.is_bastion_flex_shape
      content {
        ocpus = shape_config.value
      }
  }

  display_name        = "${local.cluster_name}-bastion"
  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
    user_data           = base64encode(data.template_file.bastion_config.rendered)
  }
  source_details {
    source_id   = var.use_standard_image ? data.oci_core_images.linux.images.0.id : var.custom_bastion_image
    source_type = "image"
  }

  create_vnic_details {
    subnet_id = local.bastion_subnet_id
  }
} 

resource "null_resource" "cluster" { 
  depends_on = [oci_core_cluster_network.cluster_network, oci_core_instance.bastion, oci_core_volume_attachment.bastion_volume_attachment ] 
  triggers = { 
    cluster_instances = join(", ", local.cluster_instances_names)
  } 
    
  provisioner "file" {
    source        = "playbooks"
    destination   = "/home/opc/"
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content        = templatefile("${path.module}/inventory.tpl", {  
      bastion_name = oci_core_instance.bastion.display_name, 
      bastion_ip = oci_core_instance.bastion.private_ip, 
      compute = var.node_count > 0 ? zipmap(local.cluster_instances_names, local.cluster_instances_ips) : zipmap([],[])
      public_subnet = data.oci_core_subnet.public_subnet.cidr_block, 
      private_subnet = data.oci_core_subnet.private_subnet.cidr_block, 
      nfs = var.node_count > 0 ? local.cluster_instances_names[0] : "",
      scratch_nfs = var.use_scratch_nfs && var.node_count > 0,
      cluster_nfs = var.use_cluster_nfs,
      cluster_nfs_path = var.cluster_nfs_path,
      scratch_nfs_path = var.scratch_nfs_path,
      cluster_network = var.cluster_network,
      slurm = var.slurm,
      spack = var.spack,
      bastion_block = var.bastion_block, 
      scratch_nfs_type = local.scratch_nfs_type,
      bastion_mount_ip = local.bastion_mount_ip,
      cluster_mount_ip = local.mount_ip,
      autoscaling = var.node_count > 0 ? false : true,
      cluster_name = local.cluster_name
      })

    destination   = "/home/opc/playbooks/inventory"
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.private_key_pem
    destination = "/home/opc/.ssh/cluster.key"
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.private_key_pem
    destination = "/home/opc/.ssh/id_rsa"
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content     = var.node_count > 0 ? join("\n",local.cluster_instances_ips) : "\n"
    destination = "/tmp/hosts"
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "configure.sh"
    destination = "/tmp/configure.sh"
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "remote-exec" {
    inline = [
      "chmod 600 /home/opc/.ssh/cluster.key",
      "chmod 600 /home/opc/.ssh/id_rsa",
      "chmod a+x /tmp/configure.sh",
      "/tmp/configure.sh"
    ]
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
}

resource "null_resource" "autoscaling" {
  depends_on = [oci_core_cluster_network.cluster_network, oci_core_instance.bastion, oci_core_volume_attachment.bastion_volume_attachment ] 

  count = var.node_count > 0 ? 0 : 1 

  provisioner "file" {
    source      = "autoscaling"
    destination = "/home/opc/"
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content        = templatefile("${path.module}/autoscaling/variables.tpl", {  
      bastion_name = oci_core_instance.bastion.display_name, 
      bastion_ip = oci_core_instance.bastion.private_ip, 
      compute = var.node_count > 0 ? zipmap(local.cluster_instances_names, local.cluster_instances_ips) : zipmap([],[])
      public_subnet = data.oci_core_subnet.public_subnet.cidr_block,
      public_subnet_id = local.bastion_subnet_id,
      private_subnet = data.oci_core_subnet.private_subnet.cidr_block, 
      private_subnet_id = local.subnet_id,
      nfs = var.node_count > 0 ? local.cluster_instances_names[0] : "",
      scratch_nfs = var.use_scratch_nfs && var.node_count > 0,
      scratch_nfs_path = var.scratch_nfs_path,
      cluster_network = var.cluster_network,
      spack = var.spack,
      bastion_block = var.bastion_block, 
      scratch_nfs_type = local.scratch_nfs_type,
      bastion_mount_ip = local.bastion_mount_ip,
      cluster_mount_ip = local.mount_ip,
      scratch_nfs_type_cluster = var.scratch_nfs_type_cluster,
      scratch_nfs_type_pool = var.scratch_nfs_type_pool,
      bastion_block_volume_performance = var.bastion_block_volume_performance,
      marketplace_listing = var.marketplace_listing,
      instance_pool_ocpus = var.instance_pool_ocpus,
      image = var.image,
      use_marketplace_image = var.use_marketplace_image,
      boot_volume_size = var.boot_volume_size,
      instance_pool_shape = var.instance_pool_shape,
      cluster_network_shape = var.cluster_network_shape,
      ad = var.ad,
      targetCompartment = var.targetCompartment,
      region = var.region,
      tenancy_ocid = var.tenancy_ocid,
      vcn_subnet = var.vcn_subnet,
      cluster_block_volume_size = var.cluster_block_volume_size,
      cluster_block_volume_performance = var.cluster_block_volume_performance,
      ssh_cidr = var.ssh_cidr,
      use_cluster_nfs = var.use_cluster_nfs,
      cluster_nfs_path = var.cluster_nfs_path,
      bastion_block = var.bastion_block,
      bastion_mount_ip = local.bastion_mount_ip
      })

    destination   = "/home/opc/autoscaling/tf_init/variables.tf"
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.public_key_openssh
    destination   = "/home/opc/.ssh/id_rsa.pub" 
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "remote-exec" {
    inline = [
      "chmod 755 /home/opc/autoscaling/*.sh",
      "chmod 755 /home/opc/autoscaling/crontab/*.sh",
      "sudo yum install -y terraform"
      ]
    connection {
      host        = oci_core_instance.bastion.public_ip
      type        = "ssh"
      user        = "opc"
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

}

