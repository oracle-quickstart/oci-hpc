#!/bin/bash

set -u

# Redirect all output to /var/log/reset.log with append
exec > /var/log/healthchecks/latest_gpu_reset.log 2>&1

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
}

FAIL=0
TIMEOUT=60
NODENAME=$(hostname)

log "=== Starting GPU reset for $NODENAME ==="
log "Script invoked as: $0 $*"

# Function to check if a systemd service exists
service_exists() {
    sudo systemctl list-unit-files | grep -qx "$1"
}

run_cmd() {
    log "Running: $*"
    timeout "$TIMEOUT" "$@" >/dev/null 2>&1
    rc=$?
    if [ $rc -eq 0 ]; then
        log "SUCCESS: $*"
    else
        FAIL=1
        log "FAILED (rc=$rc): $*"
    fi
    return $rc
}

run_cmd sudo systemctl stop nvidia-cdi-refresh.path
run_cmd sudo systemctl stop nvidia-cdi-refresh.service
run_cmd sudo systemctl stop nvidia-dcgm.service
run_cmd sudo systemctl stop nvidia-persistenced.service
run_cmd sudo systemctl stop nvidia-fabricmanager.service
# check if dcgm-exporter.service exists before stopping
if service_exists dcgm-exporter.service; then
    run_cmd sudo systemctl stop dcgm-exporter.service
else
    log "Service dcgm-exporter.service not present"
fi
run_cmd sudo systemctl stop slurmd
run_cmd sudo modprobe -r nvidia_drm
run_cmd sudo nvidia-smi -r

# Always attempt to run below commands, regardless of earlier failures
run_cmd sudo modprobe nvidia_drm
run_cmd sudo systemctl start slurmd
# check if dcgm-exporter.service exists before starting
if service_exists dcgm-exporter.service; then
    run_cmd sudo systemctl start dcgm-exporter.service
else
    log "Service dcgm-exporter.service not present"
fi
run_cmd sudo systemctl start nvidia-fabricmanager.service
run_cmd sudo systemctl start nvidia-persistenced.service
run_cmd sudo systemctl start nvidia-dcgm.service
run_cmd sudo systemctl start nvidia-cdi-refresh.service
run_cmd sudo systemctl start nvidia-cdi-refresh.path

if [ "$FAIL" -eq 0 ]; then
    log "=== GPU reset completed successfully for $NODENAME ==="
else
    log "=== GPU reset FAILED for $NODENAME ==="
fi

exit $FAIL