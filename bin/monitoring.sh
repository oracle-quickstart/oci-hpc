#!/bin/bash
#
# Cluster init configuration script
#
echo monitoring.sh
if [ $# -eq 0 ] 
then
  cluster_name=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.cluster_name`
else
  cluster_name=$1
fi

echo "ClusterName:" $cluster_name

source $(dirname "${0}")/setup_environment.sh

bash $(dirname "${0}")/setup_os_packages.sh
bash $(dirname "${0}")/setup_python_packages.sh
bash $(dirname "${0}")/setup_ansible.sh

bash $(dirname "${0}")/setup_run_ansible.sh /config/playbooks/inventory /config/playbooks/monitoring.yml
