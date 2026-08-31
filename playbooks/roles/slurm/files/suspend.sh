#!/bin/bash
exec >> /var/log/slurm/suspend.log 2>&1
# Expand the hostlist from the first argument
hosts=$(scontrol show hostnames "$1")

source /etc/os-release
echo "$(date)"
/config/venv/${ID^}_${VERSION_ID}_$(uname -m)/oci/bin/python3 /config/mgmt/manage.py nodes terminate --nodes "$(echo "$hosts" | paste -sd, -)" --no-wait
