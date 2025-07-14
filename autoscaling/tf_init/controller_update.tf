
locals {
  controller_path = "${var.autoscaling_folder}/clusters/${local.cluster_name}"
}

resource "null_resource" "create_path" {
  provisioner "local-exec" {
    command = "mkdir -p ${local.controller_path}"
  }
}

resource "local_file" "hosts" {
    depends_on = [null_resource.create_path,oci_core_cluster_network.cluster_network]
    content     = join("\n", local.cluster_instances_ips)
    filename = "${local.controller_path}/hosts_${local.cluster_name}"
  }

resource "local_file" "inventory" {
  depends_on          = [oci_core_cluster_network.cluster_network, oci_core_cluster_network.cluster_network]
  content        = templatefile("${local.controller_path}/inventory.tpl", {  
    controller_name = var.controller_name,
    controller_ip = var.controller_ip, 
    backup_name = var.backup_name,
    backup_ip = var.backup_ip,
    login_name = var.login_name,
    login_ip = var.login_ip,
    monitoring_name = var.monitoring_name,
    monitoring_ip = var.monitoring_ip,
    compute = var.node_count > 0 ? zipmap(local.cluster_instances_names, local.cluster_instances_ips) : zipmap([],[])
    public_subnet = var.public_subnet, 
    private_subnet = var.private_subnet, 
    rdma_network = cidrhost(var.rdma_subnet, 0),
    rdma_netmask = cidrnetmask(var.rdma_subnet),
    zone_name = var.zone_name,
    dns_entries = var.dns_entries,
    vcn_compartment = var.vcn_compartment,
    nfs = var.use_scratch_nfs ? local.cluster_instances_names[0] : "",
    scratch_nfs = var.use_scratch_nfs,
    cluster_nfs = var.use_cluster_nfs,
    home_nfs = var.home_nfs,
    create_fss = var.create_fss,
    home_fss = var.home_fss,
    mount_target_count = var.mount_target_count,
    nfs_mount_target_IPs = var.nfs_mount_target_IPs,
    manual_multiple_mount_target = var.manual_multiple_mount_target,
    add_nfs = var.add_nfs,
    slurm_nfs_path = var.slurm_nfs_path,
    rack_aware = var.rack_aware,
    nfs_target_path = var.nfs_target_path,
    nfs_source_IP = var.nfs_source_IP,
    nfs_source_path = var.nfs_source_path,
    nfs_options = var.nfs_options,
    add_lfs = var.add_lfs,
    lfs_target_path = var.lfs_target_path,
    lfs_source_IP = var.lfs_source_IP,
    lfs_source_path = var.lfs_source_path,
    lfs_options = var.lfs_options,
    localdisk = var.localdisk,
    log_vol = var.log_vol,
    redundancy = var.redundancy,
    cluster_nfs_path = var.cluster_nfs_path,
    scratch_nfs_path = var.scratch_nfs_path,
    cluster_network = var.cluster_network,
    slurm = var.slurm,
    pyxis = var.pyxis,
    enroot = var.enroot,
    spack = var.spack,
    ldap = var.ldap,
    controller_block = var.controller_block,
    login_block = var.login_block,
    scratch_nfs_type = local.scratch_nfs_type,
    controller_mount_ip = var.controller_mount_ip,
    login_mount_ip = var.login_mount_ip,
    cluster_mount_ip = local.mount_ip,
    cluster_name = local.cluster_name,
    shape = var.cluster_network ? var.cluster_network_shape : var.instance_pool_shape,
    instance_pool_ocpus=local.instance_pool_ocpus,
    queue=var.queue,
    instance_type=var.instance_type,
    cluster_monitoring=var.cluster_monitoring,
    autoscaling_monitoring = var.autoscaling_monitoring,
    unsupported = var.unsupported,
    hyperthreading = var.hyperthreading,
    privilege_sudo = var.privilege_sudo,
    privilege_group_name = var.privilege_group_name,
    latency_check = var.latency_check
    controller_username = var.controller_username,
    compute_username = var.compute_username,
    pam = var.pam,
    sacct_limits = var.sacct_limits,
    use_compute_agent=var.use_compute_agent,
    healthchecks=var.healthchecks,
    change_hostname=var.change_hostname,
    hostname_convention=var.hostname_convention,
    ons_topic_ocid=var.ons_topic_ocid
    })
  filename   = "${local.controller_path}/inventory"
}


resource "null_resource" "configure" {
  depends_on          = [oci_core_cluster_network.cluster_network,local_file.inventory,local_file.hosts]
  provisioner "local-exec" {
    command = "timeout 60m ${var.scripts_folder}/configure_as.sh ${local.cluster_name}"  
  }
}
