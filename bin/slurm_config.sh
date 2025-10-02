#!/bin/bash
#
# Regenerate Slurm Config
#
# Add --initial as argument if you need to restart slurm from scratch (Removes the current topology file)


scripts=`realpath $0`
folder=`dirname $scripts`
conf_folder=$folder/../conf/
playbooks_path=/config/playbooks/


if [[ ${@: -1} == "--INITIAL" || ${@: -1} == "--initial" || ${@: -1} == "-INITIAL" || ${@: -1} == "-initial" ]]
then
   sudo rm /etc/slurm/topology.conf 
   sudo /usr/sbin/slurmctld -c
fi