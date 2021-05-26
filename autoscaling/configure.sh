#!/bin/bash
#
# Cluster init configuration script
#

#
# wait for cloud-init completion on the bastion host
#

scripts=`realpath $0`
folder=`dirname $scripts`
execution=1
playbooks_path=$folder/../playbooks/
inventory_path=$folder/clusters/$1

ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"

#
# A little waiter function to make sure all the nodes are up before we start configure 
#

echo "Waiting for SSH to come up" 

for host in $(cat $inventory_path/hosts_$1) ; do
  r=0 
  echo "validating connection to: ${host}"
  while ! ssh ${ssh_options} opc@${host} uptime ; do

	if [[ $r -eq 10 ]] ; then 
		  execution=0
		  break
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

if [[ $execution -eq 1 ]] ; then
  ANSIBLE_HOST_KEY_CHECKING=False ansible all -m setup --tree /tmp/ansible > /dev/null 2>&1
  ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook $playbooks_path/new_nodes.yml -i $inventory_path/inventory
else

	cat <<- EOF > /tmp/motd
	At least one of the cluster nodes has been innacessible during installation. Please validate the hosts and re-run: 
    ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook $playbooks_path/new_nodes.yml -i $inventory_path/inventory
EOF
fi 
