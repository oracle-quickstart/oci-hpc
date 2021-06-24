#!/bin/bash
#
# Cluster destroy script
scripts=`realpath $0`
folder=`dirname $scripts`
playbooks_path=$folder/../playbooks/
inventory_path=$folder/clusters/$1

ssh_options="-i ~/.ssh/id_rsa -o StrictHostKeyChecking=no"
if [[ "$2" == "FORCE" ]]
then
    echo Force Deletion
    ANSIBLE_HOST_KEY_CHECKING=False timeout 2m ansible-playbook $playbooks_path/destroy.yml -i $inventory_path/inventory -e "force=yes"
    status_cleanup=$?
else
    ANSIBLE_HOST_KEY_CHECKING=False timeout 2m ansible-playbook $playbooks_path/destroy.yml -i $inventory_path/inventory
    status_cleanup=$?
fi
i=0
while [ $i -lt 10 ] && [ $status_cleanup -eq 124 ]
do
  ANSIBLE_HOST_KEY_CHECKING=False timeout 2m ansible-playbook $playbooks_path/destroy.yml -i $inventory_path/inventory -e "force=yes"
  status_cleanup=$?
  ((i++))
  echo $i
done
exit $status_cleanup
