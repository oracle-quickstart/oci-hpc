#!/bin/bash
#
# Cluster init configuration script
#

#
# wait for cloud-init completion on the bastion host
#

ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"
sudo cloud-init status --wait

#
# Install ansible and other required packages
#

sudo yum makecache
sudo yum install -y ansible python-netaddr

#
# A little waiter function to make sure all the nodes are up before we start configure 
#

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

#
# Ansible will take care of key exchange and learning the host fingerprints, but for the first time we need
# to disable host key checking. 
#

ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook /home/opc/playbooks/site.yml -i /home/opc/playbooks/inventory
