#!/bin/bash
exec >> /var/log/slurm/suspend.log 2>&1
# Expand the hostlist from the first argument
hosts=$(scontrol show hostnames "$1")

source /etc/os-release
for host in $hosts
do
    echo $(date)
    /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/bin/python3 /config/mgmt/manage.py nodes terminate --nodes "$host"
done