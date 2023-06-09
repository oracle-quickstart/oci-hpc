
locals {
  bastion_path = "${var.autoscaling_folder}/clusters/${var.cluster_name}"
}

resource "null_resource" "create_path" {
  provisioner "local-exec" {
    command = "mkdir -p ${local.bastion_path}"
  }
}

resource "local_file" "hosts" {
    depends_on = [null_resource.create_path,oci_core_cluster_network.cluster_network]
    content     = join("\n", local.cluster_instances_ips)
    filename = "${local.bastion_path}/hosts_${var.cluster_name}"
  }

resource "local_file" "inventory" {
  depends_on          = [oci_core_cluster_network.cluster_network]
  content        = templatefile("${local.bastion_path}/inventory.tpl", {  
    bastion_name = var.bastion_name,
    bastion_ip = var.bastion_ip, 
    backup_name = var.backup_name,
    backup_ip = var.backup_ip,
    login_name = var.login_name,
    login_ip = var.login_ip,
    compute = var.node_count > 0 ? zipmap(local.cluster_instances_names, local.cluster_instances_ips) : zipmap([],[])
    public_subnet = var.public_subnet, 
    private_subnet = var.private_subnet, 
    rdma_network = cidrhost(var.rdma_subnet, 0),
    rdma_netmask = cidrnetmask(var.rdma_subnet),
    nfs = var.use_scratch_nfs ? local.cluster_instances_names[0] : "",
    scratch_nfs = var.use_scratch_nfs,
    cluster_nfs = var.use_cluster_nfs,
    home_nfs = var.home_nfs,
    create_fss = var.create_fss,
    home_fss = var.home_fss,
    add_nfs = var.add_nfs,
    slurm_nfs_path = var.slurm_nfs_path,
    rack_aware = var.rack_aware,
    nfs_target_path = var.nfs_target_path,
    nfs_source_IP = var.nfs_source_IP,
    nfs_source_path = var.nfs_source_path,
    nfs_options = var.nfs_options,
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
    bastion_block = var.bastion_block,
    scratch_nfs_type = local.scratch_nfs_type,
    bastion_mount_ip = var.bastion_mount_ip,
    cluster_mount_ip = local.mount_ip,
    cluster_name = local.cluster_name,
    shape = var.cluster_network ? var.cluster_network_shape : var.instance_pool_shape,
    instance_pool_ocpus=local.instance_pool_ocpus,
    queue=var.queue,
    instance_type=var.instance_type,
    monitoring=var.monitoring,
    autoscaling_monitoring = var.autoscaling_monitoring,
    unsupported = var.unsupported,
    hyperthreading = var.hyperthreading,
    privilege_sudo = var.privilege_sudo,
    privilege_group_name = var.privilege_group_name,
    latency_check = var.latency_check
    bastion_username = var.bastion_username,
    compute_username = var.compute_username,
    pam = var.pam,
    sacct_limits = var.sacct_limits
    })
  filename   = "${local.bastion_path}/inventory"
}


resource "null_resource" "configure" {
  depends_on          = [oci_core_cluster_network.cluster_network,local_file.inventory,local_file.hosts]
  provisioner "local-exec" {
    command = "timeout 60m ${var.scripts_folder}/configure_as.sh ${local.cluster_name}"  
  }
}
