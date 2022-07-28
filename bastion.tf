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

resource "oci_resourcemanager_private_endpoint" "rms_private_endpoint" {
  count = var.private_deployment ? 1 : 0
  compartment_id = var.targetCompartment
  display_name   = "rms_private_endpoint"
  description    = "rms_private_endpoint_description"
  vcn_id         = local.vcn_id
  subnet_id      = local.subnet_id
}

resource "oci_core_instance" "bastion" {
  depends_on          = [local.bastion_subnet]
  availability_domain = var.bastion_ad
  compartment_id      = var.targetCompartment
  shape               = var.bastion_shape

  dynamic "shape_config" {
    for_each = local.is_bastion_flex_shape
      content {
        ocpus = shape_config.value
        memory_in_gbs = var.bastion_custom_memory ? var.bastion_memory : 16 * shape_config.value
      }
  }
  agent_config {
    is_management_disabled = true
    }
  display_name        = "${local.cluster_name}-bastion"

  freeform_tags = {
    "cluster_name" = local.cluster_name
    "parent_cluster" = local.cluster_name
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
    user_data           = base64encode(data.template_file.bastion_config.rendered)
  }
  source_details {
//    source_id   = var.use_standard_image ? data.oci_core_images.linux.images.0.id : local.custom_bastion_image_ocid
    source_id = local.bastion_image
    boot_volume_size_in_gbs = var.bastion_boot_volume_size
    source_type = "image"
  }

  create_vnic_details {
    subnet_id = local.bastion_subnet_id
    assign_public_ip = local.bastion_bool_ip
  }
} 

resource "null_resource" "bastion" { 
  depends_on = [oci_core_instance.bastion, oci_core_volume_attachment.bastion_volume_attachment ] 
  triggers = { 
    bastion = oci_core_instance.bastion.id
  } 

  provisioner "remote-exec" {
    inline = [
      "sudo mkdir -p /opt/oci-hpc",      
      "sudo chown ${var.bastion_username}:${var.bastion_username} /opt/oci-hpc/",
      "mkdir -p /opt/oci-hpc/bin",
      "mkdir -p /opt/oci-hpc/playbooks"
      ]
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    source        = "playbooks"
    destination   = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "autoscaling"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "bin"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "conf"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
    provisioner "file" {
    source      = "logs"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    source      = "samples"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" { 
    content        = templatefile("${path.module}/configure.tpl", { 
      configure = var.configure
    })
    destination   = "/tmp/configure.conf"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.private_key_pem
    destination = "/home/${var.bastion_username}/.ssh/cluster.key"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }


  provisioner "remote-exec" {
    inline = [
      "chmod 600 /home/${var.bastion_username}/.ssh/cluster.key",
      "cp /home/${var.bastion_username}/.ssh/cluster.key /home/${var.bastion_username}/.ssh/id_rsa",
      "chmod a+x /opt/oci-hpc/bin/*.sh",
      "timeout 60m /opt/oci-hpc/bin/bastion.sh"
      ]
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
}
resource "null_resource" "cluster" { 
  depends_on = [null_resource.bastion, oci_core_cluster_network.cluster_network, oci_core_instance.bastion, oci_core_volume_attachment.bastion_volume_attachment ] 
  triggers = { 
    cluster_instances = join(", ", local.cluster_instances_names)
  } 

  provisioner "file" {
    content        = templatefile("${path.module}/inventory.tpl", {  
      bastion_name = oci_core_instance.bastion.display_name, 
      bastion_ip = oci_core_instance.bastion.private_ip,
      backup_name = var.slurm_ha ? oci_core_instance.backup[0].display_name : "",
      backup_ip = var.slurm_ha ? oci_core_instance.backup[0].private_ip: "",
      compute = var.node_count > 0 ? zipmap(local.cluster_instances_names, local.cluster_instances_ips) : zipmap([],[])
      public_subnet = data.oci_core_subnet.public_subnet.cidr_block, 
      private_subnet = data.oci_core_subnet.private_subnet.cidr_block, 
      rdma_network = cidrhost(var.rdma_subnet, 0),
      rdma_netmask = cidrnetmask(var.rdma_subnet),
      nfs = var.node_count > 0 ? local.cluster_instances_names[0] : "",
      home_nfs = var.home_nfs,
      create_fss = var.create_fss,
      home_fss = var.home_fss,
      scratch_nfs = var.use_scratch_nfs && var.node_count > 0,
      cluster_nfs = var.use_cluster_nfs,
      cluster_nfs_path = var.cluster_nfs_path,
      scratch_nfs_path = var.scratch_nfs_path,
      add_nfs = var.add_nfs,
      nfs_target_path = var.nfs_target_path,
      nfs_source_IP = local.nfs_source_IP,
      nfs_source_path = var.nfs_source_path,
      nfs_options = var.nfs_options,
      cluster_network = var.cluster_network,
      slurm = var.slurm,
      rack_aware = var.rack_aware,
      slurm_nfs_path = var.add_nfs ? var.nfs_source_path : var.cluster_nfs_path
      spack = var.spack,
      ldap = var.ldap,
      bastion_block = var.bastion_block, 
      scratch_nfs_type = local.scratch_nfs_type,
      bastion_mount_ip = local.bastion_mount_ip,
      cluster_mount_ip = local.mount_ip,
      autoscaling = var.autoscaling,
      cluster_name = local.cluster_name,
      shape = var.cluster_network ? var.cluster_network_shape : var.instance_pool_shape,
      instance_pool_ocpus = var.instance_pool_ocpus,
      queue=var.queue,
      monitoring = var.monitoring,
      hyperthreading = var.hyperthreading,
      bastion_username = var.bastion_username,
      compute_username = var.compute_username,
      autoscaling_monitoring = var.autoscaling_monitoring,
      autoscaling_mysql_service = var.autoscaling_mysql_service,
      monitoring_mysql_ip = var.autoscaling_monitoring && var.autoscaling_mysql_service ? oci_mysql_mysql_db_system.monitoring_mysql_db_system[0].ip_address : "localhost",
      admin_password = var.admin_password,
      admin_username = var.autoscaling_mysql_service ? var.admin_username : "root",
      enroot = var.enroot,
      pyxis = var.pyxis,
      privilege_sudo = var.privilege_sudo,
      privilege_group_name = var.privilege_group_name,
      latency_check = var.latency_check
      })

    destination   = "/opt/oci-hpc/playbooks/inventory"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }


  provisioner "file" {
    content     = var.node_count > 0 ? join("\n",local.cluster_instances_ips) : "\n"
    destination = "/tmp/hosts"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content        = templatefile(var.inst_prin ? "${path.module}/autoscaling/provider_inst_prin.tpl" : "${path.module}/autoscaling/provider_user.tpl", {  
      api_user_ocid = var.api_user_ocid, 
      api_fingerprint = var.api_fingerprint,
      private_key_path = "/opt/oci-hpc/autoscaling/credentials/key.pem",
      tenancy_ocid = var.tenancy_ocid
      })

    destination   = "/opt/oci-hpc/autoscaling/tf_init/provider.tf"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content        = templatefile("${path.module}/queues.conf", {  
      cluster_network = var.cluster_network,
      marketplace_listing = var.marketplace_listing,
      image = local.image_ocid,
      use_marketplace_image = var.use_marketplace_image,
      boot_volume_size = var.boot_volume_size,
      shape = var.cluster_network ? var.cluster_network_shape : var.instance_pool_shape
      ad = var.ad,
      targetCompartment = var.targetCompartment,
      instance_pool_ocpus = var.instance_pool_ocpus,
      instance_pool_memory = var.instance_pool_memory,
      instance_pool_custom_memory = var.instance_pool_custom_memory,
      queue=var.queue,
      hyperthreading = var.hyperthreading
      })

    destination   = "/opt/oci-hpc/conf/queues.conf"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  
  provisioner "file" {
    content        = templatefile("${path.module}/conf/variables.tpl", {  
      bastion_name = oci_core_instance.bastion.display_name, 
      bastion_ip = oci_core_instance.bastion.private_ip, 
      backup_name = var.slurm_ha ? oci_core_instance.backup[0].display_name : "",
      backup_ip = var.slurm_ha ? oci_core_instance.backup[0].private_ip: "",
      compute = var.node_count > 0 ? zipmap(local.cluster_instances_names, local.cluster_instances_ips) : zipmap([],[])
      public_subnet = data.oci_core_subnet.public_subnet.cidr_block,
      public_subnet_id = local.bastion_subnet_id,
      private_subnet = data.oci_core_subnet.private_subnet.cidr_block, 
      private_subnet_id = local.subnet_id,
      nfs = var.node_count > 0 ? local.cluster_instances_names[0] : "",
      scratch_nfs = var.use_scratch_nfs && var.node_count > 0,
      scratch_nfs_path = var.scratch_nfs_path,
      slurm = var.slurm,
      rack_aware = var.rack_aware,
      slurm_nfs_path = var.add_nfs ? var.nfs_source_path : var.cluster_nfs_path
      spack = var.spack,
      ldap = var.ldap,
      bastion_block = var.bastion_block, 
      scratch_nfs_type = local.scratch_nfs_type,
      bastion_mount_ip = local.bastion_mount_ip,
      cluster_mount_ip = local.mount_ip,
      scratch_nfs_type_cluster = var.scratch_nfs_type_cluster,
      scratch_nfs_type_pool = var.scratch_nfs_type_pool,
      bastion_block_volume_performance = var.bastion_block_volume_performance,
      region = var.region,
      tenancy_ocid = var.tenancy_ocid,
      vcn_subnet = var.vcn_subnet,
      cluster_block_volume_size = var.cluster_block_volume_size,
      cluster_block_volume_performance = var.cluster_block_volume_performance,
      ssh_cidr = var.ssh_cidr,
      use_cluster_nfs = var.use_cluster_nfs,
      cluster_nfs_path = var.cluster_nfs_path,
      bastion_block = var.bastion_block,
      bastion_mount_ip = local.bastion_mount_ip,
      home_nfs = var.home_nfs,
      create_fss = var.create_fss,
      home_fss = var.home_fss,
      add_nfs = var.add_nfs,
      nfs_target_path = var.nfs_target_path,
      nfs_source_IP = local.nfs_source_IP,
      nfs_source_path = var.nfs_source_path,
      nfs_options = var.nfs_options,
      monitoring = var.monitoring,
      hyperthreading = var.hyperthreading,
      unsupported = var.unsupported,
      autoscaling_monitoring = var.autoscaling_monitoring,
      enroot = var.enroot,
      pyxis = var.pyxis,
      privilege_sudo = var.privilege_sudo,
      privilege_group_name = var.privilege_group_name,
      latency_check = var.latency_check,
      private_deployment = var.private_deployment
      })

    destination   = "/opt/oci-hpc/conf/variables.tf"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

provisioner "file" {
    content        = templatefile("${path.module}/initial_mon.tpl", {  
      cluster_ocid=local.cluster_ocid,
      shape = var.cluster_network ? var.cluster_network_shape : var.instance_pool_shape,
      queue=var.queue,
      cluster_network = var.cluster_network,
      ocids = join(",", local.cluster_instances_ids),
      hostnames = join(",", local.cluster_instances_names),
      ips = join(",", local.cluster_instances_ips)
      })

    destination   = "/tmp/initial.mon"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    content     = base64decode(var.api_user_key)
    destination   = "/opt/oci-hpc/autoscaling/credentials/key.initial" 
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "remote-exec" {
    inline = [
      "chmod 755 /opt/oci-hpc/autoscaling/crontab/*.sh",
      "chmod 755 /opt/oci-hpc/autoscaling/credentials/key.sh",
      "/opt/oci-hpc/autoscaling/credentials/key.sh /opt/oci-hpc/autoscaling/credentials/key.initial /opt/oci-hpc/autoscaling/credentials/key.pem > /opt/oci-hpc/autoscaling/credentials/key.log",
      "chmod 600 /opt/oci-hpc/autoscaling/credentials/key.pem",
      "echo ${var.configure} > /tmp/configure.conf",
      "timeout 2h /opt/oci-hpc/bin/configure.sh",
      "exit_code=$?",
      "/opt/oci-hpc/bin/initial_monitoring.sh",
      "exit $exit_code"     ]
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.bastion_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
}
