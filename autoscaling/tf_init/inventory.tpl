[bastion]
${bastion_name} ansible_host=${bastion_ip} ansible_user=opc role=bastion
[compute]
%{ for host, ip in compute ~}
${host} ansible_host=${ip} ansible_user=opc role=compute
%{ endfor ~}
[nfs]
${nfs}
[all:children]
bastion
compute
[all:vars]
ansible_connection=ssh
ansible_user=opc
rdma_network=192.168.168.0
rdma_netmask=255.255.252.0
public_subnet=${public_subnet} 
private_subnet=${private_subnet}
nvme_path=/mnt/localdisk/
scratch_nfs = ${scratch_nfs}
home_nfs = ${home_nfs} 
cluster_nfs = ${cluster_nfs}
cluster_nfs_path = ${cluster_nfs_path}
scratch_nfs_path = ${scratch_nfs_path}
cluster_network = ${cluster_network}
slurm = ${slurm}
spack = ${spack} 
bastion_block = ${bastion_block} 
scratch_nfs_type = ${scratch_nfs_type}
bastion_mount_ip = ${bastion_mount_ip}
cluster_mount_ip = ${cluster_mount_ip}
autoscaling = true
cluster_name = ${cluster_name}
shape=${shape}
instance_pool_ocpus=${instance_pool_ocpus}
add_nfs=${add_nfs}
nfs_target_path=${nfs_target_path}
nfs_source_IP=${nfs_source_IP}
nfs_source_path=${nfs_source_path}
nfs_options=${nfs_options}