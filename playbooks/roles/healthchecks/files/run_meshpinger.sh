#!/bin/bash

if [ "$1" == "-h" ]; then
  echo "Usage: ./run_meshpinger.sh [options]"
  echo "INFO:"
  echo "Meshpinger is a tool for validating network layer connectivity between RDMA NICs on a"
  echo "cluster network in OCI. The tool is capable of initiating ICMP ping from every RDMA NIC"
  echo "port on the cluster network to every other RDMA NIC port on the same cluster network and"
  echo "reporting back the success/failure status of the pings performed in the form of logs"

  echo "Running the tool before starting workload on a cluster network should serve as a good precheck"
  echo "step to gain confidence on the network reachability between RDMA NICs. Typical causes for"
  echo "reachability failures that the tool can help pinpoint are,"
  echo "1. Link down on the RDMA NIC"
  echo "2. RDMA interface initialization or configuration issues including IP address assignment to"
  echo "the interface"
  echo "3. Insufficient ARP table size on the node to store all needed peer mac addresses"
  echo " "
  echo "Options:"
  echo "  -h           Display this help message"
  echo "  [arg1]       Enter either --clustername or --hostlist"
  echo "  [arg2]       Enter the clustername or the path of the hostlist based on arg1"
  # Exit the script after showing the help message
  exit 0
fi

if [ $# -gt 0 ]; then
  if [ "$1" == "--clustername" ]; then
    cluster_name=$2
  else
    cat $2 > /tmp/all_hosts
  fi
else
  cluster_name=`cat /etc/ansible/hosts | grep cluster_name | awk '{print $3}'`
fi

date
eval "$(ssh-agent -s)" >/dev/null ; ssh-add ~/.ssh/id_rsa >/dev/null

if [ -z "$cluster_name" ]; then
  if [ -f "$2" ]; then
    echo "Using $2 as hostlist"
  else
     echo "The clustername is empty, running on all hosts"
     cat /etc/hosts | grep .local.vcn | awk '{print $2}' > /tmp/all_hosts
  fi
else
  echo "Clustername is $2"
  cat /etc/hosts | grep .local.vcn | grep ${cluster_name} | awk '{print $2}' > /tmp/all_hosts
fi
output_file="/tmp/failed_nodes"
/opt/oci-hpc/healthchecks/meshpinger_bm/run_meshpinger --hostlistfile /tmp/all_hosts --singlesubnet --ping_timeout 100 2>&1 | grep "INCOM\|DELAY" | awk '{print $6}' | sort -u | tee ${output_file}

if [ ! -s "$output_file" ]; then
  echo "No nodes have RDMA connections unreachable. The list of tested nodes is at /tmp/all_hosts"
fi