#!/bin/bash
#
# Cluster init configuration script
#
sudo cloud-init status --wait

source $(dirname "${0}")/setup_environment.sh

bash $(dirname "${0}")/setup_os_packages.sh
bash $(dirname "${0}")/setup_ansible.sh

echo "Backup setup complete. VENV_PATH=${VENV_PATH}"
