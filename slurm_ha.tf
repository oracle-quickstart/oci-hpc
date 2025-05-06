resource "oci_core_volume_attachment" "backup_volume_attachment" {
  count           = var.controller_block && var.slurm_ha ? 1 : 0
  attachment_type = "iscsi"
  volume_id       = oci_core_volume.controller_volume[0].id
  instance_id     = oci_core_instance.backup[0].id
  display_name    = "${local.cluster_name}-backup-volume-attachment"
  device          = "/dev/oracleoci/oraclevdb"
  is_shareable    = true
}

resource "oci_core_instance" "backup" {
  count               = var.slurm_ha ? 1 : 0
  depends_on          = [oci_core_subnet.public-subnet]
  availability_domain = var.controller_ad
  compartment_id      = var.targetCompartment
  shape               = var.controller_shape

  dynamic "shape_config" {
    for_each = local.is_controller_flex_shape
    content {
      ocpus         = shape_config.value
      memory_in_gbs = var.controller_custom_memory ? var.controller_memory : 16 * shape_config.value
    }
  }
  agent_config {
    is_management_disabled = true
  }
  display_name = "${local.cluster_name}-backup"

  freeform_tags = {
    "cluster_name"   = local.cluster_name
    "parent_cluster" = local.cluster_name
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
    user_data           = base64encode(data.template_file.controller_config.rendered)
  }
  source_details {
    //    source_id   = var.use_standard_image ? data.oci_core_images.linux.images.0.id : local.custom_controller_image_ocid
    source_id               = local.controller_image
    boot_volume_size_in_gbs = var.controller_boot_volume_size
    boot_volume_vpus_per_gb = 30
    source_type             = "image"
  }

  create_vnic_details {
    subnet_id        = local.controller_subnet_id
    assign_public_ip = local.controller_bool_ip
  }
}

resource "null_resource" "backup" {
  count      = var.slurm_ha ? 1 : 0
  depends_on = [oci_core_instance.backup]
  triggers = {
    backup = oci_core_instance.backup[0].id
  }

  provisioner "remote-exec" {
    inline = [
      "#!/bin/bash",
      "sudo mkdir -p /opt/oci-hpc",
      "sudo chown ${var.controller_username}:${var.controller_username} /opt/oci-hpc/",
      "mkdir -p /opt/oci-hpc/bin",
      "mkdir -p /opt/oci-hpc/playbooks"
    ]
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    source      = "playbooks"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "autoscaling"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "bin"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "conf"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    source      = "logs"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    source      = "samples"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    content = templatefile("${path.module}/configure.tpl", {
      configure = var.configure
    })
    destination = "/tmp/configure.conf"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.private_key_pem
    destination = "/home/${var.controller_username}/.ssh/cluster.key"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }


  provisioner "remote-exec" {
    inline = [
      "#!/bin/bash",
      "chmod 600 /home/${var.controller_username}/.ssh/cluster.key",
      "cp /home/${var.controller_username}/.ssh/cluster.key /home/${var.controller_username}/.ssh/id_rsa",
      "chmod a+x /opt/oci-hpc/bin/*.sh",
      "timeout --foreground 60m /opt/oci-hpc/bin/controller.sh"
    ]
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
}
resource "null_resource" "cluster_backup" {
  count      = var.slurm_ha ? 1 : 0
  depends_on = [null_resource.backup, oci_core_compute_cluster.compute_cluster, oci_core_cluster_network.cluster_network, oci_core_instance.backup]
  triggers = {
    cluster_instances = join(", ", local.cluster_instances_names)
  }

  provisioner "file" {
    content = templatefile("${path.module}/inventory.tpl", {
      controller_name           = oci_core_instance.controller.display_name,
      controller_ip             = oci_core_instance.controller.private_ip,
      backup_name               = var.slurm_ha ? oci_core_instance.backup[0].display_name : "",
      backup_ip                 = var.slurm_ha ? oci_core_instance.backup[0].private_ip : "",
      login_name                = var.login_node ? oci_core_instance.login[0].display_name : "",
      login_ip                  = var.login_node ? oci_core_instance.login[0].private_ip : "",
      monitoring_name           = var.monitoring_node ? oci_core_instance.monitoring[0].display_name : "",
      monitoring_ip             = var.monitoring_node ? oci_core_instance.monitoring[0].private_ip : "",
      compute                   = var.node_count > 0 ? zipmap(local.cluster_instances_names, local.cluster_instances_ips) : zipmap([], [])
      public_subnet             = data.oci_core_subnet.public_subnet.cidr_block,
      private_subnet            = data.oci_core_subnet.private_subnet.cidr_block,
      rdma_network              = cidrhost(var.rdma_subnet, 0),
      rdma_netmask              = cidrnetmask(var.rdma_subnet),
      zone_name                 = local.zone_name,
      dns_entries               = var.dns_entries,
      vcn_compartment           = var.vcn_compartment,
      nfs                       = var.node_count > 0 ? local.cluster_instances_names[0] : "",
      home_nfs                  = var.home_nfs,
      create_fss                = var.create_fss,
      home_fss                  = var.home_fss,
      scratch_nfs               = var.use_scratch_nfs && var.node_count > 0,
      cluster_nfs               = var.use_cluster_nfs,
      cluster_nfs_path          = var.cluster_nfs_path,
      scratch_nfs_path          = var.scratch_nfs_path,
      add_nfs                   = var.add_nfs,
      nfs_target_path           = var.nfs_target_path,
      nfs_source_IP             = local.nfs_source_IP,
      nfs_source_path           = var.nfs_source_path,
      nfs_options               = var.nfs_options,
      add_lfs                   = var.add_lfs,
      lfs_target_path           = var.lfs_target_path,
      lfs_source_IP             = local.luster_IP,
      lfs_source_path           = var.lfs_source_path,
      lfs_options               = var.lfs_options,
      localdisk                 = var.localdisk,
      log_vol                   = var.log_vol,
      redundancy                = var.redundancy,
      cluster_network           = var.cluster_network,
      use_compute_agent         = var.use_compute_agent,
      slurm                     = var.slurm,
      slurm_nfs_path            = var.slurm_nfs ? var.nfs_source_path : var.cluster_nfs_path,
      rack_aware                = var.rack_aware,
      spack                     = var.spack,
      ldap                      = var.ldap,
      controller_block          = var.controller_block,
      login_block               = var.login_block,
      scratch_nfs_type          = local.scratch_nfs_type,
      controller_mount_ip       = local.controller_mount_ip,
      login_mount_ip            = local.login_mount_ip,
      cluster_mount_ip          = local.mount_ip,
      autoscaling               = var.autoscaling,
      cluster_name              = local.cluster_name,
      shape                     = var.cluster_network ? var.cluster_network_shape : var.instance_pool_shape,
      instance_pool_ocpus       = local.instance_pool_ocpus,
      queue                     = var.queue,
      cluster_monitoring        = var.cluster_monitoring,
      hyperthreading            = var.hyperthreading,
      controller_username       = var.controller_username,
      compute_username          = var.compute_username,
      autoscaling_monitoring    = var.autoscaling_monitoring,
      autoscaling_mysql_service = var.autoscaling_mysql_service,
      monitoring_mysql_ip       = var.autoscaling_monitoring && var.autoscaling_mysql_service ? oci_mysql_mysql_db_system.monitoring_mysql_db_system[0].ip_address : "localhost",
      admin_password            = var.admin_password,
      admin_username            = var.autoscaling_mysql_service ? var.admin_username : "root",
      enroot                    = var.enroot,
      pyxis                     = var.pyxis,
      pam                       = var.pam,
      sacct_limits              = var.sacct_limits,
      privilege_sudo            = var.privilege_sudo,
      privilege_group_name      = var.privilege_group_name,
      latency_check             = var.latency_check,
      inst_prin                 = var.inst_prin,
      region                    = var.region,
      tenancy_ocid              = var.tenancy_ocid,
      api_fingerprint           = var.api_fingerprint,
      api_user_ocid             = var.api_user_ocid,
      healthchecks              = var.healthchecks,
      change_hostname           = var.change_hostname,
      hostname_convention       = var.hostname_convention,
      change_hostname           = var.change_hostname,
      hostname_convention       = var.hostname_convention,
      ons_topic_ocid            = local.topic_id
    })

    destination = "/opt/oci-hpc/playbooks/inventory"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }


  provisioner "file" {
    content     = var.node_count > 0 ? join("\n", local.cluster_instances_ips) : "\n"
    destination = "/tmp/hosts"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content = templatefile(var.inst_prin ? "${path.module}/autoscaling/provider_inst_prin.tpl" : "${path.module}/autoscaling/provider_user.tpl", {
      api_user_ocid    = var.api_user_ocid,
      api_fingerprint  = var.api_fingerprint,
      private_key_path = "/opt/oci-hpc/autoscaling/credentials/key.pem",
      tenancy_ocid     = var.tenancy_ocid
    })

    destination = "/opt/oci-hpc/autoscaling/tf_init/provider.tf"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content = templatefile("${path.module}/queues.conf", {
      cluster_network             = var.cluster_network,
      use_compute_agent           = var.use_compute_agent,
      compute_cluster             = var.compute_cluster,
      marketplace_listing         = var.marketplace_listing,
      image                       = local.image_ocid,
      use_marketplace_image       = var.use_marketplace_image,
      boot_volume_size            = var.boot_volume_size,
      shape                       = var.cluster_network ? var.cluster_network_shape : var.instance_pool_shape,
      region                      = var.region,
      ad                          = var.use_multiple_ads ? join(" ", [var.ad, var.secondary_ad, var.third_ad]) : var.ad,
      private_subnet              = var.private_subnet,
      private_subnet_id           = var.private_subnet_id,
      targetCompartment           = var.targetCompartment,
      instance_pool_ocpus         = local.instance_pool_ocpus,
      instance_pool_memory        = var.instance_pool_memory,
      instance_pool_custom_memory = var.instance_pool_custom_memory,
      queue                       = var.queue,
      hyperthreading              = var.hyperthreading,
      cluster_name                = local.cluster_name,
      change_hostname             = var.change_hostname,
      hostname_convention         = var.hostname_convention

    })

    destination = "/opt/oci-hpc/conf/queues.conf"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content = templatefile("${path.module}/conf/variables.tpl", {
      controller_name                     = oci_core_instance.controller.display_name,
      controller_ip                       = oci_core_instance.controller.private_ip,
      backup_name                         = var.slurm_ha ? oci_core_instance.backup[0].display_name : "",
      backup_ip                           = var.slurm_ha ? oci_core_instance.backup[0].private_ip : "",
      login_name                          = var.login_node ? oci_core_instance.login[0].display_name : "",
      login_ip                            = var.login_node ? oci_core_instance.login[0].private_ip : "",
      monitoring_name                     = var.monitoring_node ? oci_core_instance.monitoring[0].display_name : "",
      monitoring_ip                       = var.monitoring_node ? oci_core_instance.monitoring[0].private_ip : "",
      compute                             = var.node_count > 0 ? zipmap(local.cluster_instances_names, local.cluster_instances_ips) : zipmap([], [])
      public_subnet                       = data.oci_core_subnet.public_subnet.cidr_block,
      public_subnet_id                    = local.controller_subnet_id,
      private_subnet                      = data.oci_core_subnet.private_subnet.cidr_block,
      private_subnet_id                   = local.subnet_id,
      rdma_subnet                         = var.rdma_subnet,
      nfs                                 = var.node_count > 0 && var.use_scratch_nfs ? local.cluster_instances_names[0] : "",
      scratch_nfs                         = var.use_scratch_nfs && var.node_count > 0,
      scratch_nfs_path                    = var.scratch_nfs_path,
      use_scratch_nfs                     = var.use_scratch_nfs,
      slurm                               = var.slurm,
      slurm_nfs_path                      = var.add_nfs ? var.nfs_source_path : var.cluster_nfs_path
      rack_aware                          = var.rack_aware,
      spack                               = var.spack,
      ldap                                = var.ldap,
      controller_block                    = var.controller_block,
      login_block                         = var.login_block,
      scratch_nfs_type                    = local.scratch_nfs_type,
      controller_mount_ip                 = local.controller_mount_ip,
      login_mount_ip                      = local.login_mount_ip,
      cluster_mount_ip                    = local.mount_ip,
      scratch_nfs_type_cluster            = var.scratch_nfs_type_cluster,
      scratch_nfs_type_pool               = var.scratch_nfs_type_pool,
      controller_block_volume_performance = var.controller_block_volume_performance,
      region                              = var.region,
      tenancy_ocid                        = var.tenancy_ocid,
      vcn_subnet                          = var.vcn_subnet,
      vcn_id                              = local.vcn_id,
      vcn_compartment                     = var.vcn_compartment,
      zone_name                           = local.zone_name,
      dns_entries                         = var.dns_entries,
      cluster_block_volume_size           = var.cluster_block_volume_size,
      cluster_block_volume_performance    = var.cluster_block_volume_performance,
      ssh_cidr                            = var.ssh_cidr,
      use_cluster_nfs                     = var.use_cluster_nfs,
      cluster_nfs_path                    = var.cluster_nfs_path,
      home_nfs                            = var.home_nfs,
      create_fss                          = var.create_fss,
      home_fss                            = var.home_fss,
      add_nfs                             = var.add_nfs,
      nfs_target_path                     = var.nfs_target_path,
      nfs_source_IP                       = local.nfs_source_IP,
      nfs_source_path                     = var.nfs_source_path,
      nfs_options                         = var.nfs_options,
      add_lfs                             = var.add_nfs,
      lfs_target_path                     = var.lfs_target_path,
      lfs_source_IP                       = var.lfs_source_IP,
      lfs_source_path                     = var.lfs_source_path,
      lfs_options                         = var.lfs_options,
      localdisk                           = var.localdisk,
      log_vol                             = var.log_vol,
      redundancy                          = var.redundancy,
      cluster_monitoring                  = var.cluster_monitoring,
      hyperthreading                      = var.hyperthreading,
      unsupported                         = var.unsupported,
      autoscaling_monitoring              = var.autoscaling_monitoring,
      enroot                              = var.enroot,
      pyxis                               = var.pyxis,
      pam                                 = var.pam,
      sacct_limits                        = var.sacct_limits,
      privilege_sudo                      = var.privilege_sudo,
      privilege_group_name                = var.privilege_group_name,
      latency_check                       = var.latency_check,
      private_deployment                  = var.private_deployment,
      controller_username                 = var.controller_username,
      compute_username                    = var.compute_username,
      use_multiple_ads                    = var.use_multiple_ads,
      use_compute_agent                   = var.use_compute_agent,
      BIOS                                = var.BIOS,
      IOMMU                               = var.IOMMU,
      SMT                                 = var.SMT,
      virt_instr                          = var.virt_instr,
      access_ctrl                         = var.access_ctrl,
      numa_nodes_per_socket               = var.numa_nodes_per_socket,
      percentage_of_cores_enabled         = var.percentage_of_cores_enabled,
      healthchecks                        = var.healthchecks,
      change_hostname                     = var.change_hostname,
      hostname_convention                 = var.hostname_convention,
      ons_topic_ocid                      = local.topic_id
    })

    destination = "/opt/oci-hpc/conf/variables.tf"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }


  provisioner "file" {
    content     = base64decode(var.api_user_key)
    destination = "/opt/oci-hpc/autoscaling/credentials/key.initial"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "remote-exec" {
    inline = [
      "#!/bin/bash",
      "chmod 755 /opt/oci-hpc/autoscaling/crontab/*.sh",
      "chmod 755 /opt/oci-hpc/autoscaling/credentials/key.sh",
      "/opt/oci-hpc/autoscaling/credentials/key.sh /opt/oci-hpc/autoscaling/credentials/key.initial /opt/oci-hpc/autoscaling/credentials/key.pem > /opt/oci-hpc/autoscaling/credentials/key.log",
      "chmod 600 /opt/oci-hpc/autoscaling/credentials/key.pem",
    "echo ${var.configure} > /tmp/configure.conf"]
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
}


resource "oci_dns_rrset" "rrset-backup" {
  count           = var.slurm_ha && var.dns_entries ? 1 : 0
  zone_name_or_id = data.oci_dns_zones.dns_zones.zones[0].id
  domain          = "${var.slurm_ha ? oci_core_instance.backup[0].display_name : ""}.${local.zone_name}"
  rtype           = "A"
  items {
    domain = "${var.slurm_ha ? oci_core_instance.backup[0].display_name : ""}.${local.zone_name}"
    rtype  = "A"
    rdata  = var.slurm_ha ? oci_core_instance.backup[0].private_ip : ""
    ttl    = 3600
  }
  scope   = "PRIVATE"
  view_id = data.oci_dns_views.dns_views.views[0].id
}
