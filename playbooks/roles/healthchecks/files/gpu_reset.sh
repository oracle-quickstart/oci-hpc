#!/bin/bash

set -u  # Treat unset variables as errors

fail=0    # To track any kind of failure or timeout
TIMEOUT=60

# Function to check if a systemd service exists
service_exists() {
    sudo systemctl list-unit-files | grep -qx "$1"
}

run_cmd() {
    # Runs the given command with timeout and sets fail=1 on failure
    # Usage: run_cmd command args...
    timeout "$TIMEOUT" "$@" >/dev/null 2>&1 || fail=1
}

# 1
run_cmd sudo systemctl stop nvidia-cdi-refresh.path
# 2
run_cmd sudo systemctl stop nvidia-cdi-refresh.service
# 3
run_cmd sudo systemctl stop nvidia-dcgm.service
# 4
run_cmd sudo systemctl stop nvidia-persistenced.service
# 5
run_cmd sudo systemctl stop nvidia-fabricmanager.service
# 6: check if dcgm-exporter.service exists before stopping
if service_exists dcgm-exporter.service; then
    run_cmd sudo systemctl stop dcgm-exporter.service
fi
# 7
run_cmd sudo systemctl stop slurmd
# 8
run_cmd sudo modprobe -r nvidia_drm
# 9
run_cmd sudo nvidia-smi -r

# Always attempt to run commands 10-17, regardless of earlier failures
# 10
run_cmd sudo modprobe nvidia_drm
# 11
run_cmd sudo systemctl start slurmd
# 12: only if exists
if service_exists dcgm-exporter.service; then
    run_cmd sudo systemctl start dcgm-exporter.service
fi
# 13
run_cmd sudo systemctl start nvidia-fabricmanager.service
# 14
run_cmd sudo systemctl start nvidia-persistenced.service
# 15
run_cmd sudo systemctl start nvidia-dcgm.service
# 16
run_cmd sudo systemctl start nvidia-cdi-refresh.service
# 17
run_cmd sudo systemctl start nvidia-cdi-refresh.path

exit $fail