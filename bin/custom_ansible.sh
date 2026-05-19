#!/bin/bash
#
# Cluster init configuration script
#

set -Eeuo pipefail
source "$(dirname "${0}")/common.sh"
setup_bootstrap_traps "custom_ansible.sh"

#
# wait for cloud-init completion on the controller host
#
if [[ "$#" -eq 0 ]]; then
  echo "No playbook specified."
  exit 1
fi

playbook_file="/config/playbooks/${1}.yml"
if [[ ! -f "${playbook_file}" ]]; then
  echo "ERROR: playbook file not found: $playbook_file"
  exit 1
fi

source "$(dirname "${0}")/setup_environment.sh"

cluster_name=$(curl -fsL --retry 5 --retry-delay 2 -H "Authorization: Bearer Oracle" http://169.254.169.254/opc/v2/instance/freeformTags/cluster_name 2>/dev/null || true)
modified_hostname=$(curl -fsL --retry 5 --retry-delay 2 -H "Authorization: Bearer Oracle" http://169.254.169.254/opc/v2/instance/displayName 2>/dev/null || true)

if [[ -z "${cluster_name}" || "${cluster_name}" == "null" ]]; then
  echo "ERROR: unable to determine cluster_name from instance metadata"
  exit 1
fi
if [[ -z "${modified_hostname}" || "${modified_hostname}" == "null" ]]; then
  echo "ERROR: unable to determine displayName from instance metadata"
  exit 1
fi

max_attempts=3
attempt=1
wait_time=10

log=/config/logs/${modified_hostname}.log
mkdir -p "$(dirname "$log")"

exec > >(
    while IFS= read -r line; do
        printf "[%s] %s\n" "$(printf '%(%F %T)T' -1)" "$line"
    done | tee -a "$log"
) 2>&1

while [[ "${attempt}" -le "${max_attempts}" ]]; do
    echo "Attempt $attempt of $max_attempts: Configuring the node"
    if "$VENV_PATH/bin/ansible-playbook" -i "/config/playbooks/inventory_${cluster_name}" "$playbook_file" "${@:2}"; then
        echo "Ansible succeeded!"
        break
    else
        echo "Ansible failed. "
        if [[ "${attempt}" -lt "${max_attempts}" ]]; then
            echo "Retrying in ($wait_time)s ..."
            sleep "${wait_time}"
            wait_time=$((wait_time * 2))
        else
            echo "Max attempts ($max_attempts) reached. Giving up."
            exit 1
        fi
        attempt=$((attempt + 1))
    fi
done
