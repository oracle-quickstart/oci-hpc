[bastion]
${bastion_name} ansible_host=${bastion_ip} ansible_user=opc role=bastion
[slurm_backup]
%{ if backup_name != "" }${backup_name} ansible_host=${backup_ip} ansible_user=opc role=bastion%{ endif }
[compute_to_add]
[compute_configured]
%{ for host, ip in compute ~}
${host} ansible_host=${ip} ansible_user=opc role=compute
%{ endfor ~}
[compute_to_destroy]
[compute:children]
compute_to_add
compute_configured
[nfs]
${nfs}
[all:children]
bastion
compute
[all:vars]
ansible_connection=ssh
ansible_user=opc
rdma_network=192.168.128.0
rdma_netmask=255.255.240.0
public_subnet=${public_subnet} 
private_subnet=${private_subnet}
nvme_path=/mnt/localdisk/
scratch_nfs = ${scratch_nfs}
home_nfs = ${home_nfs} 
create_fss = ${create_fss} 
home_fss = ${home_fss} 
cluster_nfs = ${cluster_nfs}
cluster_nfs_path = ${cluster_nfs_path}
slurm_nfs_path = ${slurm_nfs_path}
scratch_nfs_path = ${scratch_nfs_path}
cluster_network = ${cluster_network}
slurm = ${slurm}
rack_aware = ${rack_aware}
pyxis = ${pyxis}
enroot = ${enroot}
spack = ${spack} 
bastion_block = ${bastion_block} 
scratch_nfs_type = ${scratch_nfs_type}
bastion_mount_ip = ${bastion_mount_ip}
cluster_mount_ip = ${cluster_mount_ip}
autoscaling = true
force = no
cluster_name = ${cluster_name}
shape=${shape}
instance_pool_ocpus=${instance_pool_ocpus}
add_nfs=${add_nfs}
nfs_target_path=${nfs_target_path}
nfs_source_IP=${nfs_source_IP}
nfs_source_path=${nfs_source_path}
nfs_options=${nfs_options}
ldap=${ldap}
queue=${queue}
instance_type=${instance_type}
hyperthreading=${hyperthreading}
privilege_sudo=${privilege_sudo}
privilege_group_name=${privilege_group_name}
latency_check=${latency_check}
