#!/bin/bash
#
# Cluster init configuration script
#

# wait for cloud-init completion
ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"
sudo cloud-init status --wait
#sudo yum makecache
#sudo yum install -y nc 
echo "Waiting for SSH to come up" 

for host in $(cat /tmp/hosts) ; do
  r=0 
  echo "validating connection to: ${host}"
  while ! ssh ${ssh_options} opc@${host} uptime ; do

	if [[ $r -eq 10 ]] ; then 
		  exit 1
	fi 
        
	echo "Still waiting for ${host}"

	sleep 60 
	r=$(($r + 1))
  done
done

# copy provisioning RPM from the first cluster node
arr=($(cat /tmp/hosts))
scp ${ssh_options} opc@${arr[0]}:/opt/oci-hpc/rpms/oci-hpc-provision-20190906.R-63.10.1.x86_64.rpm /tmp/
sudo rpm -Uvh /tmp/oci-hpc-provision-20190906.R-63.10.1.x86_64.rpm
sudo mkdir -p /etc/opt/oci-hpc/
cp /tmp/hosts /etc/opt/oci-hpc/hostfile


