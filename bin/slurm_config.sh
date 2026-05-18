#!/bin/bash
#
# Regenerate Slurm Config
#
# Add --initial as argument if you need to restart slurm from scratch (Removes the current topology file)

set -Eeuo pipefail
source "$(dirname "${0}")/common.sh"
setup_bootstrap_traps "slurm_config.sh"

last_arg="${@: -1}"

if [[ "${last_arg}" == "--INITIAL" || "${last_arg}" == "--initial" || "${last_arg}" == "-INITIAL" || "${last_arg}" == "-initial" ]]
then
   sudo rm -f /etc/slurm/topology.conf
   sudo /usr/sbin/slurmctld -c
fi
