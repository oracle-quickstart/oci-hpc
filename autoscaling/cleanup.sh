#!/bin/bash
#
# Cluster destroy script
scripts=`realpath $0`
folder=`dirname $scripts`
playbooks_path=$folder/../playbooks/
inventory_path=$folder/clusters/$1

ssh_options="-i ~/.ssh/id_rsa -o StrictHostKeyChecking=no"

ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook $playbooks_path/destroy.yml -i $inventory_path/inventory
