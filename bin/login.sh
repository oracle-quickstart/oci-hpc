#!/bin/bash
#
# Cluster init configuration script
#

exec > >(while IFS= read -r line; do printf "[%s] %s\n" "$(printf '%(%F %T)T' -1)" "$line"; done) 2>&1

echo "login.sh"
set -Eeuo pipefail
source "$(dirname "${0}")/common.sh"
setup_bootstrap_traps "login.sh"

if [[ "$#" -eq 0 ]]
then
  cluster_name=$(curl -fsL --retry 5 --retry-delay 2 -H "Authorization: Bearer Oracle" http://169.254.169.254/opc/v2/instance/freeformTags/cluster_name 2>/dev/null || true)
else
  cluster_name="${1}"
fi

if [[ -z "${cluster_name}" || "${cluster_name}" == "null" ]]; then
  echo "ERROR: unable to determine cluster_name from instance metadata"
  exit 1
fi

echo "ClusterName: $cluster_name"

source "$(dirname "${0}")/setup_environment.sh"

echo "Starting OS packages setup..."
bash "$(dirname "${0}")/setup_os_packages.sh"
echo "OS packages setup complete"

echo "Starting Python packages setup..."
bash "$(dirname "${0}")/setup_python_packages.sh"
echo "Python packages setup complete"

echo "Starting Ansible setup..."
bash "$(dirname "${0}")/setup_ansible.sh"
echo "Ansible setup complete"

echo "Starting Ansible playbook execution..."
bash "$(dirname "${0}")/setup_run_ansible.sh" /config/playbooks/inventory /config/playbooks/login.yml
echo "Ansible playbook execution complete"
