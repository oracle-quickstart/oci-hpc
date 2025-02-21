#!/bin/bash

# Ensure a parameter (node group) is passed
if [ -z "$1" ]; then
  echo "Usage: $0 <node-group>"
  exit 1
fi

# Loop through hostnames from scontrol output
for i in $(scontrol show hostname "$1"); do
  echo "Processing node: $i"

  # Get the OCID using a single call and correct variable expansion in jq
  ocid=$(python3 /opt/oci-hpc/bin/get_nodes_from_db.py | jq -r --arg i "$i" '.[] | select(.hostname == $i) | .ocid')

  # Check if OCID was found
  if [ -n "$ocid" ]; then
    echo "Found OCID: $ocid"
    echo "Executing: oci compute instance action --instance-id $ocid --action RESET --auth instance_principal"

    # Run the OCI command
    oci compute instance action --instance-id "$ocid" --action RESET --auth instance_principal > /dev/null
  else
    echo "No OCID found for hostname: $i"
  fi
done