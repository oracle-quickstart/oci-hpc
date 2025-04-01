#!/bin/bash
set -e

# number of times to run the nccl test to stress the GPUs and RDMA network. 
max=$1

# This assume, the hostfile  passed is already ordered based on their rackId
if [ -n "$2" ]; then
  hostfile=$2
else
  hostfile="/etc/opt/oci-hpc/hostfile.tcp"
fi

echo INPUTFILE
cat $hostfile

# The number of GPUs to use for the test.  Has to be multiplier of 8.  If not passed, all GPUs will be used.
if [ -n "$3" ]; then
  np=$3
else
  np=$((`less $hostfile | wc -l` * 8 ))
fi

logfile="nccl_run_allreduce.sh.log"

for x in $(seq 1 1 $max)
do

  echo $x
  echo $x >> $logfile
  date >> $logfile

  hostfile=$hostfile; np=$np;

  mpivars_path=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`

  if [[ "$mpivars_path" == "" ]]; then
      mpivars_path=`ls /opt/openmpi-*/bin/mpivars.sh`
  fi

  if [[ "$mpivars_path" == "" ]]; then
      echo "Could not find MPIPATH"; exit; fi

  source $mpivars_path

  first_node=`head $hostfile -n 1`
  shape=`ssh $first_node 'curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/' | jq .shape`
  if [ $shape == \"BM.GPU.H100.8\" ]
  then
    var_UCX_NET_DEVICES=eth0
  else
    echo "Use the appropriate nccl test run script for non H100 nodes"
  fi

  # all NCCL parameters are at /etc/nccl.conf on each compute node.
  mpirun --mca pml ucx \
  --bind-to numa \
  -npernode 8 \
  --mca coll ^hcoll \
  -x HCOLL_ENABLE_MCAST_ALL=0 \
  -x coll_hcoll_enable=0 \
  -x UCX_TLS=tcp \
  -x UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
  -x RX_QUEUE_LEN=8192 \
  -x IB_RX_QUEUE_LEN=8192 \
  --np $np --hostfile $hostfile  /opt/oci-hpc/nccl-test/build/all_reduce_perf -b 1G -e 16G -f 2 -g 1 >>  $logfile

  tail -n 32 $logfile


done