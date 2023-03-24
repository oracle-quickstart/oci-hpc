#!/bin/bash
#
# Cluster destroy script
scripts=`realpath $0`
folder=`dirname $scripts`
playbooks_path=$folder/../playbooks/
inventory_path=$folder/../autoscaling/clusters/$1

if [ $EUID -eq 0 ]
then
  echo "Run this script as opc or ubuntu and not as root"
  exit
fi

ssh_options="-i ~/.ssh/id_rsa -o StrictHostKeyChecking=no"
iplist=`cat $inventory_path/inventory | awk '{print $2}' | sed 's/ansible_host=//'`
if [[ "$2" == "FORCE" ]]
then
    echo Force Deletion
    ANSIBLE_HOST_KEY_CHECKING=False timeout 2m ansible-playbook $playbooks_path/destroy.yml -i $inventory_path/inventory -e "force=yes"
    status_cleanup=$?
    if [ $status_cleanup -ne 0 ]
    then
        /opt/oci-hpc/bin/resize.py remove_unreachable --nodes $iplist
        status_cleanup=$?
    fi
    exit $status_cleanup
else
    ANSIBLE_HOST_KEY_CHECKING=False timeout 2m ansible-playbook $playbooks_path/destroy.yml -i $inventory_path/inventory  -e "force=no"
    status_cleanup=$?
    exit $status_cleanup
fi