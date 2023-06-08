#!/bin/bash
set -e

# run with:
#
#     ./nccl_run_alltoall.sh  1  /home/opc/ordered_hostfile_system_name 16 


# number of times to run the nccl test to stress the GPUs and RDMA network. This is different from -n iterations parameter of nccl allreduce which is set below using $iter
max=$1

# This assume, the hostfile  passed is already ordered based on their rackId
if [ -n "$2" ]; then
  hostfile=$2
else
  hostfile="/home/opc/hostfile.tcp"
  hostfile="/etc/opt/oci-hpc/hostfile.tcp"
fi

ORDEREDMACHINEFILE="ordered_hostfile_system_name"
echo INPUTFILE
cat $hostfile

# will generate rack-aware ordered host file
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then
    python3 /home/opc/node_ordering_by_rack.py --input_file $hostfile > /dev/null
elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then
    python3 /home/ubuntu/node_ordering_by_rack.py --input_file $hostfile > /dev/null
fi

hostfile=$ORDEREDMACHINEFILE

echo ORDEREDMACHINEFILE
cat $ORDEREDMACHINEFILE


# The number of GPUs to use for the test.  Has to be multiplier of 8.  If not passed, all GPUs will be used.
if [ -n "$3" ]; then
  np=$3
else
  np=$((`less $hostfile | wc -l` * 8 ))
fi
WORLD_SIZE=$np


logfile="run_nccl_alltoall.sh.log"

for x in $(seq 1 1 $max)
do

  echo $x
  echo $x >> $logfile
  date >> $logfile 

  hostfile=$hostfile; np=$np ; iter=50;

  mpivars_path=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`
  source $mpivars_path

  if [[ "$mpivars_path" == "" ]]; then echo "Could not find MPIPATH"; exit; fi

first_node=`head $hostfile -n 1`
shape=`ssh $first_node 'curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/' | jq .shape`
if [ $shape == \"BM.GPU.B4.8\" ] || [ $shape == \"BM.GPU.A100-v2.8\" ]
then
  var_UCX_NET_DEVICES=mlx5_0:1
  var_NCCL_IB_HCA="=mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_14,mlx5_15,mlx5_16,mlx5_17,mlx5_9,mlx5_10,mlx5_11,mlx5_12"
elif [ $shape == \"BM.GPU4.8\" ]
then
  var_UCX_NET_DEVICES=mlx5_4:1
  var_NCCL_IB_HCA="=mlx5_0,mlx5_2,mlx5_6,mlx5_8,mlx5_10,mlx5_12,mlx5_14,mlx5_16,mlx5_1,mlx5_3,mlx5_7,mlx5_9,mlx5_11,mlx5_13,mlx5_15,mlx5_17"
fi

  # Use  -x NCCL_MAX_P2P_NCHANNELS=16 until NCCL 2.12 release which has a fix to allow NCCL_MAX_P2P_NCHANNELS=32 for nodes with 16 RDMA NICss
  # final version
  # you need --mca coll ^hcoll when using an image that has OFED 5.4 or newer
  mpirun --mca pml ucx \
  --bind-to numa \
  --mca coll ^hcoll \
  -x NCCL_MAX_P2P_NCHANNELS=16 \
  -x NCCL_DEBUG=WARN \
  -x NCCL_IB_SL=0 \
  -x NCCL_IB_TC=41 \
  -x NCCL_IB_QPS_PER_CONNECTION=4 \
  -x UCX_TLS=ud,self,sm \
  -x UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
  -x HCOLL_ENABLE_MCAST_ALL=0 \
  -x coll_hcoll_enable=0 \
  -x NCCL_IB_GID_INDEX=3 \
  -x NCCL_ALGO=Ring \
  -x NCCL_IB_HCA="${var_NCCL_IB_HCA}" \
  --np $np --hostfile $hostfile  -N 8 /opt/oci-hpc/nccl-test/build/alltoall_perf  -f 2 -g 1 -c 0 -n $iter  >> $logfile

  tail -n 15 $logfile


done
