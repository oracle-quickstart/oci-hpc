#!/bin/bash
#
# Regenerate Slurm Config
#

scripts=`realpath $0`
folder=`dirname $scripts`
playbooks_path=$folder/../playbooks/

ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook $playbooks_path/slurm_config.yml