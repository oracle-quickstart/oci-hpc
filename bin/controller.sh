#!/bin/bash
#
# Cluster init configuration script
#

exec > >(while IFS= read -r line; do printf "[%s] %s\n" "$(printf '%(%F %T)T' -1)" "$line"; done) 2>&1

set -Eeuo pipefail
source "$(dirname "${0}")/common.sh"
setup_bootstrap_traps "controller.sh"

echo "Starting controller setup - waiting for cloud-init..."
cloud_exit_code=0
sudo cloud-init status --wait || cloud_exit_code=$?
if [[ "${cloud_exit_code}" -gt 0 ]]; then
    # print the error, then quit for exit code 1 (non-recoverable error). Code
    # status 2 is recoverable, proceed.
    echo "Controller cloud-init reported status != 0:"
    sudo cloud-init status -l
    if [[ "${cloud_exit_code}" -eq 1 ]]; then
        exit 1
    fi
fi

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
