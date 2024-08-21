#!/bin/bash

if [ "$1" == "-h" ]; then
  echo "Usage: ./run_meshpinger.sh [options]"
  echo "Options:"
  echo "  -h           Display this help message"
  echo "  [arg1]       Enter the clustername"
  # Exit the script after showing the help message
  exit 0
fi

if [ $# -gt 0 ]; then
  cluster_name=$1
else
  cluster_name=`cat /etc/ansible/hosts | grep cluster_name | awk '{print $3}'`
fi

date
eval "$(ssh-agent -s)" >/dev/null ; ssh-add ~/.ssh/id_rsa >/dev/null

if [ -z "$cluster_name" ]; then
  echo "The clustername is empty, running on all hosts"
  cat /etc/hosts | grep .local.vcn | awk '{print $2}' > /tmp/all_hosts
else
  cat /etc/hosts | grep .local.vcn | grep ${cluster_name} | awk '{print $2}' > /tmp/all_hosts
fi
output_file="/tmp/failed_nodes"
/opt/oci-hpc/healthchecks/meshpinger_bm/run_meshpinger --hostlistfile /tmp/all_hosts --singlesubnet --ping_timeout 100 2>&1 | grep "INCOM\|DELAY" | awk '{print $6}' | sort -u | tee ${output_file}

if [ ! -s "$output_file" ]; then
  echo "No nodes have RDMA connections unreachable over RDMA. The list of tested nodes is at /tmp/all_hosts"
fi