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
intel_mpi=true
configure_nfs=true
nvme_path=/mnt/localdisk/
nfs_export_path=/mnt/localdisk/nfs-share
nfs_mount_path=/mnt/nfs-share
