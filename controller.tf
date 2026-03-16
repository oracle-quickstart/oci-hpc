resource "oci_core_volume_backup_policy" "controller_boot_volume_backup_policy" {
  count          = var.controller_boot_volume_backup ? 1 : 0
  compartment_id = var.targetCompartment
  display_name   = "${local.cluster_name}-controller_boot_volume_daily"
  schedules {
    backup_type       = var.controller_boot_volume_backup_type
    period            = var.controller_boot_volume_backup_period
    retention_seconds = var.controller_boot_volume_backup_retention_seconds
    time_zone         = var.controller_boot_volume_backup_time_zone
  }
  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "oci_core_volume_backup_policy_assignment" "boot_volume_backup_policy" {
  count      = var.controller_boot_volume_backup ? 1 : 0
  depends_on = [oci_core_volume_backup_policy.controller_boot_volume_backup_policy]
  asset_id   = oci_core_instance.controller.boot_volume_id
  policy_id  = oci_core_volume_backup_policy.controller_boot_volume_backup_policy[0].id
}

resource "oci_resourcemanager_private_endpoint" "rms_private_endpoint" {
  count          = var.private_deployment ? 1 : 0
  compartment_id = var.targetCompartment
  display_name   = "rms_private_endpoint"
  description    = "rms_private_endpoint_description"
  vcn_id         = local.vcn_id
  subnet_id      = local.subnet_id
}

resource "oci_ons_notification_topic" "grafana_alerts" {
  count          = var.alerting ? 1 : 0
  compartment_id = var.targetCompartment
  name           = "grafana-alerts-${random_pet.name.id}"
  description    = "Topic for Grafana Alerts"
  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
  }
}

resource "null_resource" "boot_volume_backup_policy" {
  depends_on = [oci_core_instance.controller, oci_core_volume_backup_policy.controller_boot_volume_backup_policy, oci_core_volume_backup_policy_assignment.boot_volume_backup_policy]
  triggers = {
    controller = oci_core_instance.controller.id
  }
}

resource "oci_core_instance" "controller" {
  depends_on          = [local.controller_subnet, oci_functions_function.function, oci_core_shape_management.controller-shape]
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
  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }
  agent_config {
    is_management_disabled = true
  }
  display_name = "${local.cluster_name}-controller"

  freeform_tags = {
    "cluster_name"    = local.cluster_name
    "controller_name" = "${local.cluster_name}-controller"
    "controller"      = "true"
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

resource "null_resource" "controller" {
  depends_on = [oci_core_instance.controller, null_resource.fss_home_dependency, null_resource.fss_config_dependency, time_sleep.dns_sleep]
  triggers = {
    controller = oci_core_instance.controller.id
  }

  provisioner "remote-exec" {
    inline = concat([
      "#!/bin/bash",
      "sudo mkdir -p /opt/oci-hpc",
      "sudo chown -R ${var.controller_username}:${var.controller_username} /opt/",
      "mkdir -p /opt/oci-hpc/bin",
      "sudo mkdir -p /config",
      "sudo chown -R ${var.controller_username}:${var.controller_username} /config/"
      ],
      var.create_fss == "new" ? [
        "echo \"${local.config_target_name}:/config /config nfs defaults,nconnect=16 0 0\" | sudo tee -a /etc/fstab",
        "sudo systemctl daemon-reload",
        "for i in {1..30}; do sudo mount /config ; mountpoint -q /config && break || { echo 'Waiting for /config to be mounted...'; sleep 10 ; }; done"
      ] : [],
      [
        "sudo chown ${var.controller_username}:${var.controller_username} /config",
        "mkdir -p /config/logs",
        "sudo chown ${var.controller_username}:${var.controller_username} /config/logs",
        "mkdir -p /config/bin",
        "sudo chown ${var.controller_username}:${var.controller_username} /config/bin",
        "mkdir -p /config/key",
        "sudo chown ${var.controller_username}:${var.controller_username} /config/key"      
        ],
      var.slurm_federation ? [        
        "echo ${var.munge_key} | base64 -d > /config/key/munge.key"
      ] : [],
      [
        "mkdir -p /config/3rdparty",
        "sudo chown ${var.controller_username}:${var.controller_username} /config/3rdparty"
      ])
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "20m"
    }
  }
  provisioner "file" {
    source      = "playbooks"
    destination = "/config"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }


  provisioner "file" {
    source      = "bin"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }

  provisioner "file" {
    source      = "conf"
    destination = "/config/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }

  provisioner "file" {
    source      = "cloud-init.sh"
    destination = "/config/bin/cloud-init.sh"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }

  provisioner "file" {
    source      = "samples"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }
  provisioner "file" {
    source      = "scripts"
    destination = "/opt/oci-hpc/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.private_key_openssh
    destination = "/config/key/cluster.key"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.private_key_openssh
    destination = "/home/${var.controller_username}/.ssh/cluster.key"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }

  provisioner "file" {
    content     = tls_private_key.ssh.public_key_openssh
    destination = "/home/${var.controller_username}/.ssh/ed25519.pub"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }
  provisioner "file" {
    content     = tls_private_key.ssh.public_key_openssh
    destination = "/config/key/public"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }
  provisioner "file" {
    source      = "mgmt"
    destination = "/config/"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "10m"
    }
  }
}

resource "null_resource" "cluster" {
  depends_on = [null_resource.controller, oci_core_instance.controller]

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
      active_healthchecks      = var.active_healthchecks,
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
      slurm_federation         = var.slurm_federation,
      ip_slurmdbd              = var.ip_slurmdbd,
      wildcard_dns_domain      = var.wildcard_dns_domain,
      use_lets_encrypt_prod_ep = var.use_lets_encrypt_prod_ep
    })

    destination = "/config/playbooks/inventory"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content = templatefile("${path.module}/conf/initial_configs.conf", {
      rdma_enabled                      = var.rdma_enabled,
      stand_alone                       = var.stand_alone,
      marketplace_listing               = var.marketplace_listing,
      image                             = local.image_ocid,
      use_marketplace_image             = var.use_marketplace_image,
      boot_volume_size                  = var.boot_volume_size,
      shape                             = var.rdma_enabled ? var.cluster_network_shape : var.instance_pool_shape,
      region                            = var.region,
      ad                                = var.ad,
      private_subnet                    = data.oci_core_subnet.private_subnet.cidr_block,
      private_subnet_id                 = local.subnet_id,
      targetCompartment                 = var.targetCompartment,
      instance_pool_ocpus               = local.instance_pool_ocpus,
      instance_pool_memory              = var.instance_pool_memory,
      instance_pool_custom_memory       = var.instance_pool_custom_memory,
      queue                             = var.queue,
      hyperthreading                    = var.hyperthreading,
      cluster_name                      = local.cluster_name,
      change_hostname                   = var.change_hostname,
      hostname_convention               = var.hostname_convention,
      ondemand_partition                = var.ondemand_partition,
      ondemand_partition_count          = var.ondemand_partition_count,
      preemptible                       = var.preemptible
      public_subnet                     = data.oci_core_subnet.public_subnet.cidr_block,
      public_subnet_id                  = local.controller_subnet_id
      login_shape                       = var.login_shape,
      login_ad                          = var.login_ad,
      login_image                       = local.controller_image
      login_boot_volume_size            = var.login_boot_volume_size
      use_marketplace_image_login       = var.use_marketplace_image
      login_instance_pool_ocpus         = local.instance_pool_ocpus
      login_instance_pool_memory        = var.login_memory
      login_instance_pool_custom_memory = var.login_custom_memory
      marketplace_listing_login         = var.marketplace_listing
    })

    destination = "/config/conf/initial_configs.conf"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "file" {
    content = templatefile("${path.module}/conf/marketplace.conf", {
      hpc_option1    = var.marketplace_version_id["HPC_OL8"]
      gpu_option1    = var.marketplace_version_id["GPU_OL8_NV550"]
      gpu_option2    = var.marketplace_version_id["GPU_OL8_NV570"]
      gpu_option3    = var.marketplace_version_id["GPU_OL8_AMD632"]
      listing_id_HPC = var.marketplace_listing_id_HPC
      listing_id_GPU = var.marketplace_listing_id_GPU
    })

    destination = "/config/conf/marketplace.conf"
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }

  provisioner "remote-exec" {
    inline = [
      "#!/bin/bash",
      "chmod 600 /home/${var.controller_username}/.ssh/cluster.key",
      "sudo chown ${var.controller_username}:${var.controller_username} /config/bin",
      "cp /opt/oci-hpc/bin/compute.sh /config/bin",
      "cp /opt/oci-hpc/bin/login.sh /config/bin",
      "cp /opt/oci-hpc/bin/monitoring.sh /config/bin",
      "cp /opt/oci-hpc/bin/custom_ansible.sh /config/bin",
      "cp /opt/oci-hpc/bin/setup_ansible.sh /config/bin",
      "cp /opt/oci-hpc/bin/setup_environment.sh /config/bin",
      "cp /opt/oci-hpc/bin/setup_os_packages.sh /config/bin",
      "cp /opt/oci-hpc/bin/setup_python_packages.sh /config/bin",
      "cp /opt/oci-hpc/bin/setup_run_ansible.sh /config/bin",
      "cp /opt/oci-hpc/bin/uv_wrapper.sh /config/bin",
      "sudo chown ${var.controller_username}:${var.controller_username} /config/bin/compute.sh",
      "sudo chown ${var.controller_username}:${var.controller_username} /config/bin/login.sh",
      "sudo chown ${var.controller_username}:${var.controller_username} /config/bin/monitoring.sh",
      "sudo chown ${var.controller_username}:${var.controller_username} /config/bin/custom_ansible.sh",
      "sudo chown ${var.controller_username}:${var.controller_username} /config/bin/uv_wrapper.sh",
      "sudo chmod 775 /config/bin/compute.sh",
      "sudo chmod 775 /config/bin/login.sh",
      "sudo chmod 775 /config/bin/monitoring.sh",
      "sudo chmod 775 /config/bin/custom_ansible.sh",
      "sudo chmod 600 /config/key/cluster.key",
      "sudo chmod 775 /config/bin/cloud-init.sh",
      "sudo chmod 775 /config/bin/uv_wrapper.sh",
      "sudo chmod 777 /config/playbooks",
      "sudo chown ${var.controller_username}:${var.controller_username} /config/key/cluster.key",
      "sudo cp -pr /home/${var.controller_username}/.ssh/cluster.key /home/${var.controller_username}/.ssh/id_ed25519",
      "chmod a+x /opt/oci-hpc/bin/*.sh",
      "exit_code=$${PIPESTATUS[0]}",
    "exit $exit_code"]
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
  provisioner "remote-exec" {
    inline = [
      "#!/bin/bash",
      "timeout --foreground 60m /opt/oci-hpc/bin/controller.sh",
    ]
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
}

resource "null_resource" "configure" {
  depends_on = [null_resource.cluster, null_resource.setup_backup, oci_core_instance.controller]

  provisioner "remote-exec" {
    inline = [
      "#!/bin/bash",
      "chmod 755 /opt/oci-hpc/samples/*.sh",
      "timeout --foreground 2h /opt/oci-hpc/bin/configure.sh 2>&1 | tee /config/logs/initial_configure.log",
      "exit_code=$${PIPESTATUS[0]}",
    "exit $exit_code"]
    connection {
      host        = local.host
      type        = "ssh"
      user        = var.controller_username
      private_key = tls_private_key.ssh.private_key_pem
    }
  }
}



locals {
  current_timestamp           = timestamp()
  current_timestamp_formatted = formatdate("YYYYMMDDhhmmss", local.current_timestamp)
  rdma_nic_metric_bucket_name = format("%s_%s", "RDMA_NIC_metrics", local.current_timestamp_formatted)
  par_path                    = ".."
}
/*
saving the PAR into file: ../PAR_file_for_metrics.
this PAR is used by the scripts to upload NIC metrics to object storage (i.e. script: upload_rdma_nic_metrics.sh)
*/


resource "oci_dns_rrset" "rrset-controller" {
  count           = 1
  zone_name_or_id = data.oci_dns_zones.dns_zones.zones[0].id
  domain          = "${oci_core_instance.controller.display_name}.${local.zone_name}"
  rtype           = "A"
  items {
    domain = "${oci_core_instance.controller.display_name}.${local.zone_name}"
    rtype  = "A"
    rdata  = oci_core_instance.controller.private_ip
    ttl    = 3600
  }
  view_id = data.oci_dns_views.dns_views.views[0].id
}
