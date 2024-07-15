#!/bin/bash
#
# Regenerate Slurm Config
#
# Add --initial as argument if you need to restart slurm from scratch (Removes the current topology file)


scripts=`realpath $0`
folder=`dirname $scripts`
autoscaling_folder=$folder/../autoscaling/
conf_folder=$folder/../conf/
playbooks_path=$folder/../playbooks/

source /etc/os-release


if [[ ${@: -1} == "--INITIAL" || ${@: -1} == "--initial" || ${@: -1} == "-INITIAL" || ${@: -1} == "-initial" ]]
then
   sudo rm /etc/slurm/topology.conf 
   sudo /usr/sbin/slurmctld -c
fi
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook $playbooks_path/slurm_config.yml
if [[ ${@: -1} == "--INITIAL" || ${@: -1} == "--initial" || ${@: -1} == "-INITIAL" || ${@: -1} == "-initial" ]]
then
   for inventory in /opt/oci-hpc/autoscaling/clusters/*/inventory ; 
   do
      if [ -f $(dirname $inventory)/currently* ]
      then
         echo "Cluster is not in running state"
      else
         ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook $playbooks_path/slurm_config_as.yml -i $inventory
      fi
   done
fi