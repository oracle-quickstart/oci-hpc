#!/bin/bash
#
# Cluster init configuration script
#

# wait for cloud-init completion
ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"
sudo cloud-init status --wait
#curl -L https://bootstrap.saltstack.com -o /tmp/bootstrap_salt.sh
#chmod a+x /tmp/bootstrap_salt.sh
#/tmp/bootstrap_salt.sh -MN

sudo yum makecache
sudo yum install -y ansible python-netaddr

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

ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook /home/opc/playbooks/site.yml -i /home/opc/playbooks/inventory

# copy provisioning RPM from the first cluster node
#arr=($(cat /tmp/hosts))
#scp ${ssh_options} opc@${arr[0]}:/opt/oci-hpc/rpms/oci-hpc-provision-20190906.R-63.10.1.x86_64.rpm /tmp/
#sudo rpm -Uvh /tmp/oci-hpc-provision-20190906.R-63.10.1.x86_64.rpm
#sudo mkdir -p /etc/opt/oci-hpc/
