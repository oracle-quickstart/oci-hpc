resource "oci_core_instance" "backup" {
  count               = var.slurm_ha ? 1 : 0
  depends_on          = [oci_core_subnet.public-subnet]
  availability_domain = var.controller_ad
  compartment_id      = var.targetCompartment
  shape               = var.controller_shape
  instance_options {
        are_legacy_imds_endpoints_disabled = true

  }
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
    "cluster_name"    = local.cluster_name
    "controller_name" = oci_core_instance.controller.display_name
    "controller"      = "true"
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}${var.compute_node_ssh_key}"
    user_data           = base64encode(templatefile("${path.module}/config.controller", {
      key = tls_private_key.ssh.private_key_pem
    }))
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
    inline = concat([
      "#!/bin/bash",
      "sudo mkdir -p /opt/oci-hpc",
      "sudo chown -R ${var.controller_username}:${var.controller_username} /opt/",
      "mkdir -p /opt/oci-hpc/bin",
      "mkdir -p /opt/oci-hpc/playbooks"
      ]
    )
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
    content     = tls_private_key.ssh.private_key_pem
    destination = "/home/${var.controller_username}/.ssh/cluster.key"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

}

resource "null_resource" "setup_backup" {
  count      = var.slurm_ha ? 1 : 0
  depends_on = [null_resource.cluster, null_resource.backup]
  
  provisioner "remote-exec" {
    inline = concat([
      "#!/bin/bash",
      "sudo mkdir -p /config",
      "sudo chown -R ${var.controller_username}:${var.controller_username} /config/",
      ],
      var.add_nfs ? [
        "echo \"${local.config_target_name}:/config /config nfs defaults,nconnect=16 0 0\" | sudo tee -a /etc/fstab",
        "sudo mount /config",
      ] : [],
      [
      "chmod 600 /home/${var.controller_username}/.ssh/cluster.key",
      "cp /home/${var.controller_username}/.ssh/cluster.key /home/${var.controller_username}/.ssh/ed25519",
      "chmod a+x /opt/oci-hpc/bin/*.sh",
      "timeout --foreground 60m /opt/oci-hpc/bin/backup.sh"]
    )
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
  depends_on = [null_resource.setup_backup]

  provisioner "file" {
    content = templatefile("${path.module}/inventory.tpl", {
      controller_name          = oci_core_instance.controller.display_name,
      controller_ip            = oci_core_instance.controller.private_ip,
      backup_name              = var.slurm_ha ? oci_core_instance.backup[0].display_name : "",
      backup_ip                = var.slurm_ha ? oci_core_instance.backup[0].private_ip : "",
      monitoring_name          = var.monitoring_node ? oci_core_instance.monitoring[0].display_name : "",
      monitoring_ip            = var.monitoring_node ? oci_core_instance.monitoring[0].private_ip : "",
      public_subnet            = data.oci_core_subnet.public_subnet.cidr_block,
      private_subnet           = data.oci_core_subnet.private_subnet.cidr_block,
      rdma_network             = cidrhost(var.rdma_subnet, 0),
      rdma_netmask             = cidrnetmask(var.rdma_subnet),
      vcn_compartment          = var.vcn_compartment,
      zone_name                = local.zone_name,
      create_fss               = var.create_fss,
      shared_home              = var.shared_home,
      add_nfs                  = var.add_nfs,
      nfs_target_path          = var.nfs_target_path,
      nfs_source_IP            = local.nfs_source_IP,
      nfs_source_path          = var.nfs_source_path,
      nfs_options              = var.nfs_options,
      localdisk                = var.localdisk,
      log_vol                  = var.log_vol,
      redundancy               = var.redundancy,
      rdma_enabled             = var.rdma_enabled,
      slurm                    = var.slurm,
      slurm_version            = var.slurm_version,
      rack_aware               = var.rack_aware,
      slurm_nfs_path           = var.create_fss == "new" ? var.nfs_source_path : "/config"
      spack                    = var.spack,
      ldap                     = var.ldap,
      cluster_name             = local.cluster_name,
      shape                    = local.shape,
      instance_pool_ocpus      = local.instance_pool_ocpus,
      queue                    = var.queue,
      cluster_monitoring       = var.cluster_monitoring,
      hyperthreading           = var.hyperthreading,
      controller_username      = var.controller_username,
      compute_username         = var.compute_username,
      enroot                   = var.enroot,
      pyxis                    = var.pyxis,
      privilege_sudo           = var.privilege_sudo,
      privilege_group_name     = var.privilege_group_name,
      pam                      = var.pam,
      sacct_limits             = var.sacct_limits,
      region                   = var.region,
      tenancy_ocid             = var.tenancy_ocid,
      healthchecks             = var.healthchecks,
      change_hostname          = var.change_hostname,
      hostname_convention      = var.hostname_convention,
      queue_ocid               = local.queue_ocid,
      ons_topic_ocid           = local.topic_id,
      ondemand_partition       = var.ondemand_partition,
      ondemand_partition_count = var.ondemand_partition_count,
      grafana_initial_creds    = base64encode(random_password.grafana_admin_pwd.result),
      add_lfs                  = var.add_lfs,
      lfs_target_path          = var.lfs_target_path,
      lfs_source_IP            = local.lustre_IP,
      lfs_source_path          = var.lfs_source_path,
      lfs_options              = var.lfs_options,
      metrics_stream_ocid      = local.metrics_stream_ocid,
      mysql_admin_password     = var.mysql_admin_password,
      mysql_admin_username     = var.mysql_admin_username,
      mysql_service_host       = local.mysql_service_host,
      wildcard_dns_domain      = var.wildcard_dns_domain,
      use_lets_encrypt_prod_ep = var.use_lets_encrypt_prod_ep
    })


    destination = "/opt/oci-hpc/playbooks/inventory"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

}


resource "oci_dns_rrset" "rrset-backup" {
  count           = var.slurm_ha ? 1 : 0
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
