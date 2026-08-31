resource "oci_core_instance" "backup" {
  count               = var.slurm_ha ? 1 : 0
  depends_on          = [oci_core_subnet.public-subnet, oci_core_shape_management.controller-shape]
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
      memory_in_gbs = var.controller_custom_memory ? var.controller_memory : (var.controller_shape == "VM.DenseIO.E5.Flex" || var.controller_shape == "VM.DenseIO.E6.Ax.Flex" ? 12 : 16) * shape_config.value
    }
  }
  agent_config {
    is_management_disabled = true
  }
  display_name = "${local.cluster_name}-backup"

  freeform_tags = {
    "cluster_name"        = local.cluster_name
    "config_fss_hostname" = local.config_fss_hostname
    "controller_name"     = oci_core_instance.controller.display_name
    "slurm_backup"        = "true"
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}${var.compute_node_ssh_key}"
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
      "sudo chown -R ${local.cluster_admin_user}:${local.cluster_admin_user} /opt/",
      "mkdir -p /opt/oci-hpc/bin",
      "mkdir -p /opt/oci-hpc/playbooks/group_vars/all"
      ]
    )
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    source      = "${path.module}/playbooks"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "${path.module}/bin"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    source      = "${path.module}/conf"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    source      = "${path.module}/logs"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "file" {
    source      = "${path.module}/samples"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.private_key_pem
    destination = "/home/${local.cluster_admin_user}/.ssh/cluster.key"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
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
      "sudo chown -R ${local.cluster_admin_user}:${local.cluster_admin_user} /config/",
      "sudo sh -c 'sed -Ei \"/^[[:space:]]*[^#[:space:]]+[[:space:]]+\\/config([[:space:]]+|$)/d\" /etc/fstab'",
      "echo \"${local.config_fss_hostname}:/config /config nfs defaults,nconnect=16 0 0\" | sudo tee -a /etc/fstab",
      "echo 'Configured /config mount in /etc/fstab.'",
      "for i in {1..30}; do sudo mount /config ; mountpoint -q /config && break || { echo 'Waiting for /config to be mounted...'; sleep 10 ; }; done",
      "chmod 600 /home/${local.cluster_admin_user}/.ssh/cluster.key",
      "cp /home/${local.cluster_admin_user}/.ssh/cluster.key /home/${local.cluster_admin_user}/.ssh/ed25519",
      "chmod a+x /opt/oci-hpc/bin/*.sh",
      "set -o pipefail",
      "timeout --foreground 60m /opt/oci-hpc/bin/backup.sh 2>&1 | tee -a /config/logs/initial_configure.log",
      "exit_code=$${PIPESTATUS[0]}",
      "if [ $${exit_code} -ne 0 ]; then",
      "  echo 'backup.sh failed; dumping diagnostics'",
      "  echo '--- tail /config/logs/initial_configure.log ---'",
      "  tail -n 100 /config/logs/initial_configure.log || true",
      "  echo '--- controller artifacts ---'",
      "  ls -l /config/playbooks/inventory /config/playbooks/inventory_* /config/key/* 2>/dev/null || true",
      "  echo '--- logs directory ---'",
      "  ls -l /config/logs || true",
      "  echo '--- running processes ---'",
      "  ps -ef | egrep 'backup.sh|ansible-galaxy|configure.sh|timeout --foreground' | egrep -v egrep || true",
      "fi",
      "exit $exit_code"]
    )
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
}

resource "null_resource" "cluster_backup" {
  count      = var.slurm_ha ? 1 : 0
  depends_on = [null_resource.setup_backup]

  provisioner "file" {
    content = templatefile("${path.module}/inventory.tpl", {
      controller_name                = oci_core_instance.controller.display_name,
      controller_ip                  = oci_core_instance.controller.private_ip,
      backup_name                    = var.slurm_ha ? oci_core_instance.backup[0].display_name : "",
      backup_ip                      = var.slurm_ha ? oci_core_instance.backup[0].private_ip : "",
      monitoring_name                = var.monitoring_node ? oci_core_instance.monitoring[0].display_name : "",
      monitoring_ip                  = var.monitoring_node ? oci_core_instance.monitoring[0].private_ip : "",
      public_subnet                  = data.oci_core_subnet.public_subnet.cidr_block,
      private_subnet                 = data.oci_core_subnet.private_subnet.cidr_block,
      vcn_cidr                       = data.oci_core_vcn.vcn.cidr_block,
      rdma_network                   = cidrhost(var.rdma_subnet, 0),
      rdma_netmask                   = cidrnetmask(var.rdma_subnet),
      vcn_compartment                = var.vcn_compartment,
      zone_name                      = local.zone_name,
      create_fss                     = var.create_fss,
      shared_home                    = var.shared_home,
      add_nfs                        = var.add_nfs,
      nfs_target_path                = var.nfs_target_path,
      nfs_source_IP                  = local.nfs_source_IP,
      nfs_source_path                = var.nfs_source_path,
      nfs_options                    = var.nfs_options,
      config_fss_hostname            = local.config_fss_hostname,
      localdisk                      = var.localdisk,
      log_vol                        = var.localdisk && var.log_vol,
      redundancy                     = var.localdisk && var.log_vol && var.redundancy,
      rdma_enabled                   = var.rdma_enabled,
      slurm                          = var.slurm,
      slurm_version                  = var.slurm_version,
      slurm_nfs_path                 = "/config",
      spack                          = var.spack,
      ldap                           = var.ldap,
      cluster_name                   = local.cluster_name,
      cluster_admin_user             = local.cluster_admin_user,
      shape                          = local.compute_shape,
      instance_pool_ocpus            = local.instance_pool_ocpus,
      queue                          = var.queue,
      permanent                      = true,
      cluster_monitoring             = var.cluster_monitoring,
      grafana_ldap_auth_enabled      = var.grafana_ldap_auth_enabled && var.ldap && var.cluster_monitoring,
      hyperthreading                 = var.hyperthreading,
      pyxis                          = var.pyxis,
      dgxc_benchmarking              = var.dgxc_benchmarking,
      privilege_sudo                 = var.privilege_sudo,
      privilege_group_name           = var.privilege_group_name,
      pam                            = var.pam,
      sacct_limits                   = var.sacct_limits,
      region                         = var.region,
      tenancy_ocid                   = var.tenancy_ocid,
      healthchecks                   = var.healthchecks,
      active_healthchecks            = var.active_healthchecks,
      change_hostname                = var.change_hostname,
      hostname_convention            = var.hostname_convention,
      queue_ocid                     = local.queue_ocid,
      ons_topic_ocid                 = local.topic_id,
      ondemand_partition             = var.ondemand_partition,
      ondemand_partition_count       = var.ondemand_partition_count,
      add_lfs                        = var.add_lfs,
      lfs_target_path                = var.lfs_target_path,
      lfs_source_IP                  = local.lustre_IP,
      lfs_source_path                = var.lfs_source_path,
      lfs_options                    = var.lfs_options,
      metrics_stream_ocid            = local.metrics_stream_ocid,
      mysql_admin_username           = local.mysql_admin_username,
      mysql_service_host             = local.mysql_service_host,
      slurm_job_monitoring           = local.slurm_job_monitoring_enabled,
      slurm_monitoring_mysql_backend = local.slurm_monitoring_mysql_backend,
      slurm_monitoring_db_host       = local.slurm_monitoring_db_host,
      slurm_federation               = var.slurm_federation,
      ip_slurmdbd                    = var.ip_slurmdbd,
      wildcard_dns_domain            = var.wildcard_dns_domain,
      use_lets_encrypt_prod_ep       = var.use_lets_encrypt_prod_ep,
      create_bucket                  = var.create_bucket,
      bucket_access_key              = local.bucket_access_key,
      bucket_secret_key              = local.bucket_secret_key,
      ocir_namespace                 = local.ocir_namespace,
      write_node_function_ocid       = oci_functions_function.function.id
    })
    destination = "/opt/oci-hpc/playbooks/inventory"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content = local.monitoring_group_vars

    destination = "/opt/oci-hpc/playbooks/group_vars/all/monitoring.yml"
    connection {
      host        = local.host_backup
      type        = "ssh"
      user        = local.cluster_admin_user
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
  view_id = data.oci_dns_views.dns_views.views[0].id
}
