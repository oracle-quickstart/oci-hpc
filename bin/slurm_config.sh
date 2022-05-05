#!/bin/bash
#
# Regenerate Slurm Config
#


scripts=`realpath $0`
folder=`dirname $scripts`
autoscaling_folder=$folder/../autoscaling/
conf_folder=$folder/../conf/
playbooks_path=$folder/../playbooks/

if [[ `cat $conf_folder/queues.conf | grep instance_keyword |  uniq -c -d | wc -l ` == 0 ]];
then
   ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook $playbooks_path/slurm_config.yml
else
   echo "There are some duplicates instance_keyword lines, please make them unique"   
fi
