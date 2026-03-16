#!/bin/bash
#
# Cluster init configuration script
#
sudo cloud-init status --wait
cloud_exit_code=$?
if [[ ${cloud_exit_code} -gt 0 ]]; then
    # print the error, then quit for exit code 1 (non-recoverable error). Code
    # status 2 is recoverable, proceed.
    echo "Controller cloud-init reported status != 0:"
    sudo cloud-init status -l
    if [[ ${cloud_exit_code} -eq 1 ]]; then
        exit 1
    fi
fi
set -eu -o pipefail

source "$(dirname "${0}")/setup_environment.sh"

bash "$(dirname "${0}")/setup_os_packages.sh"
bash "$(dirname "${0}")/setup_python_packages.sh"
bash "$(dirname "${0}")/setup_ansible.sh"

echo "Controller setup complete. VENV_PATH=${VENV_PATH}"
