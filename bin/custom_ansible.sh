#!/bin/bash
#
# Cluster init configuration script
#

#
# wait for cloud-init completion on the controller host
#
if [ $# -eq 0 ]
then
  echo "No playbook specified."
  exit 1
fi
cluster_name=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.cluster_name`
modified_hostname=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .displayName`


source /etc/os-release
export UV_INSTALL_DIR=/config/venv/${ID^}_${VERSION_ID}_$(uname -m)/
export VENV_PATH=${UV_INSTALL_DIR}/oci

max_attempts=3
attempt=1
wait_time=10

log=/config/logs/${modified_hostname}.log

while [ $attempt -le $max_attempts ]; do
    echo "Attempt $attempt of $max_attempts: Configuring the node" | tee -a $log
    $VENV_PATH/bin/ansible-playbook -i /config/playbooks/inventory_$cluster_name /config/playbooks/${1}.yml ${@:2} 2>&1 | tee -a $log
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "Ansible succeeded!" | tee -a $log
        break
    else
        echo "Ansible failed. " | tee -a $log
        if [ $attempt -lt $max_attempts ]; then
            echo "Retrying in ($wait_time)s ..." | tee -a $log
            sleep $wait_time
            wait_time=$((wait_time * 2))
        else
            echo "Max attempts ($max_attempts) reached. Giving up." | tee -a $log
        fi
        ((attempt++))
    fi
done