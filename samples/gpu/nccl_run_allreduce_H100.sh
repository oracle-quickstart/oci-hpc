#!/bin/bash
set -e

# number of times to run the nccl test to stress the GPUs and RDMA network. This is different from -n iterations parameter of nccl allreduce which is set below using $iter
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

  hostfile=$hostfile; np=$np ; iter=20;

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
    var_NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_12,mlx5_13,mlx5_14,mlx5_15,mlx5_16,mlx5_17"
  else
    echo "Use the appropriate nccl test run script for non H100 nodes"
  fi

  mpirun --mca pml ucx \
  --bind-to numa \
  -npernode 8 \
  --mca coll ^hcoll \
  -x NCCL_CROSS_NIC=2 \
  -x NCCL_DEBUG=WARN \
  -x NCCL_CUMEM_ENABLE=0 \
  -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
  -x NCCL_IB_QPS_PER_CONNECTION=1 \
  -x NCCL_IB_GID_INDEX=3 \
  -x NCCL_IB_TC=41 \
  -x NCCL_IB_SL=0 \
  -x NCCL_IB_TIMEOUT=22 \
  -x NCCL_NET_PLUGIN=none \
  -x HCOLL_ENABLE_MCAST_ALL=0 \
  -x coll_hcoll_enable=0 \
  -x UCX_TLS=tcp \
  -x UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
  -x RX_QUEUE_LEN=8192 \
  -x IB_RX_QUEUE_LEN=8192 \
  -x NCCL_BUFFSIZE=16777216 \
  -x NCCL_SOCKET_IFNAME=${var_UCX_NET_DEVICES} \
  -x NCCL_IGNORE_CPU_AFFINITY=1 \
  -x NCCL_IB_HCA="${var_NCCL_IB_HCA}" \
  -x NCCL_TOPO_FILE=~/H100-topology.xml \
  --np $np --hostfile $hostfile  /opt/oci-hpc/nccl-test/build/all_reduce_perf -b 1G -e 16G -f 2 -g 1 >>  $logfile

  tail -n 32 $logfile

done


  # If NCCL version is lower than 2.20.3, it is recommended to use the topology filefor optimal performances 
  # -x NCCL_TOPO_FILE=~/H100-topology.xml \

  # If NCCL version is lower than 2.20.3, it is recommended to use 
  # -x NCCL_CROSS_NIC=0 for multiple subnets and large scale jobs (>16 nodes)
  # -x NCCL_CROSS_NIC=1 for single subnets and small scale jobs (<16 nodes)

  # If NCCL version is higher than 2.20.3, the absolute max NCCL throughput at large message size will be obtained with
  # -x NCCL_MIN_NCHANNELS=32 \ But it does take some processing power away from the GPU for networking gains and is not recommended while running jobs. 