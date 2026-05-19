#!/bin/bash
#
# Cluster init configuration script
#

exec > >(while IFS= read -r line; do printf "[%s] %s\n" "$(printf '%(%F %T)T' -1)" "$line"; done) 2>&1

set -Eeuo pipefail
source "$(dirname "$0")/common.sh"
setup_bootstrap_traps "configure.sh"

echo "Starting cluster configuration..."

if [[ -n "${1:-}" ]]; then
  playbook="${1}"
else
  playbook="/config/playbooks/site.yml"
fi

if [[ -n "${2:-}" ]]; then
  inventory="${2}"
else
  inventory="/etc/ansible/hosts"
fi

echo "Using playbook: $playbook"
echo "Using inventory: $inventory"

source "$(dirname "$0")/setup_environment.sh"

echo "VENV OS Architecture: $VENV_OS_ARCH"

if [[ -f /config/playbooks/inventory ]]; then
  echo "Processing inventory file..."
  sed -i "s|##VENV_OS_ARCH##|$VENV_OS_ARCH|g" /config/playbooks/inventory
  sudo cp /config/playbooks/inventory /etc/ansible/hosts
fi

username=$(grep '^compute_username=' "$inventory" 2>/dev/null | tail -n 1 | awk -F "=" '{print $2}' || true)
clustername=$(grep '^cluster_name=' "$inventory" 2>/dev/null | tail -n 1 | awk -F "=" '{print $2}' || true)
if [[ -z "${username}" ]]; then
  username="$USER"
fi
clustername="${clustername:-unknown}"

echo "Username: $username"
echo "Cluster name: $clustername"

if [[ -f /etc/ansible/hosts ]]; then
  sudo chown "$username:$username" /etc/ansible/hosts
fi
if [[ -f /config/playbooks/inventory ]]; then
  sudo cp /config/playbooks/inventory "/config/playbooks/inventory_${clustername}"
  sudo chown "$username:$username" "/config/playbooks/inventory_${clustername}"
  echo "Inventory processing complete"
fi

export ANSIBLE_CONFIG=/etc/ansible/ansible.cfg

echo "VENV_PATH: $VENV_PATH"
echo "ANSIBLE_CONFIG: $ANSIBLE_CONFIG"


run_with_retry 3 10 "Ansible setup" env ANSIBLE_HOST_KEY_CHECKING=False timeout 5m \
  "${VENV_PATH}/bin/ansible" --private-key ~/.ssh/cluster.key all -m setup --tree /tmp/ansible
echo "Ansible setup complete, starting playbook execution..."
ANSIBLE_HOST_KEY_CHECKING=False "${VENV_PATH}/bin/ansible-playbook" --private-key ~/.ssh/cluster.key "$playbook" -i "$inventory"


echo "Cluster configuration complete"
