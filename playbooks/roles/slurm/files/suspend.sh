#!/bin/bash
exec > /var/log/slurm/suspend.log 2>&1
# Expand the hostlist from the first argument
hosts=$(scontrol show hostnames "$1")

for host in $hosts
do
    /config/venv/bin/python3 /config/mgmt/manage.py nodes terminate --nodes "$host"
done