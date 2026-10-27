#!/bin/bash

# Check both modules on every service start, including starts outside Ansible.
deadline=$((SECONDS + 900))
while true; do
  ready=true
  for module in oci-hpc-rdma-configure oci-rdma-authentication; do
    state=$(jq -r '.state // "UNKNOWN"' "/var/run/oci-hpc/${module}.json" 2>/dev/null) || state=unavailable
    if [ "$state" != "COMPLETED" ]; then
      echo "Waiting for OCA module ${module}: state=${state}" >&2
      ready=false
    fi
  done
  if [ "$ready" = true ]; then
    exit 0
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "OCA RDMA configuration did not complete within 900 seconds; see /var/log/oracle-cloud-agent/plugins/oci-hpc/." >&2
    exit 0
  fi
  sleep 10
done
