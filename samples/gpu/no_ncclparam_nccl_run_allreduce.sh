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


# This script defaults to running all_reduce_perf, but can run other NCCL tests if launched with
# EXEC=all_gather_perf sbatch -N8 ./nccl_run_allreduce_H100_200.sbatch

if [[ -z "${EXEC}" ]]; then
  export EXEC_CMD="/opt/oci-hpc/nccl-test/build/all_reduce_perf"
else
  export EXEC_CMD="/opt/oci-hpc/nccl-test/build/${EXEC}"
fi

if [ ! -f ${EXEC_CMD} ]; then
    echo "Test executable ${EXEC_CMD} not found!"
    exit 1
fi

ORDEREDMACHINEFILE="ordered_hostfile_system_name"
ORDEREDRANKMACHINEFILE="rankfile_system_name"
echo INPUTFILE
cat $hostfile


source /etc/os-release
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then
    python3 /home/opc/node_ordering_by_rack.py --input_file $hostfile > /dev/null
elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then
    python3 /home/ubuntu/node_ordering_by_rack.py --input_file $hostfile > /dev/null
fi

hostfile=$ORDEREDMACHINEFILE
rankfile=$ORDEREDRANKMACHINEFILE

echo ORDEREDMACHINEFILE
cat $ORDEREDMACHINEFILE
echo ORDEREDRANKMACHINEFILE
cat $ORDEREDRANKMACHINEFILE

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

  rankfile=$rankfile; np=$np ; iter=20;

  mpivars_path=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`

  if [[ "$mpivars_path" == "" ]]; then
      mpivars_path=`ls /opt/openmpi-*/bin/mpivars.sh`
  fi

  if [[ "$mpivars_path" == "" ]]; then
      echo "Could not find MPIPATH"; exit; fi

  source $mpivars_path
  hpcx_path=`ls /opt/hpcx-*/nccl_rdma_sharp_plugin/lib/libnccl-net.so`
  if [[ "$hpcx_path" == "" ]]; then
      hpcx_path=none
  fi
  first_node=`head $hostfile -n 1`

  export NCCL_DEBUG=WARN


  shape=`ssh $first_node 'curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/' | jq .shape`
  if [ $shape == \"BM.GPU.B4.8\" ] || [ $shape == \"BM.GPU.A100-v2.8\" ]
  then
    var_UCX_NET_DEVICES=mlx5_0:1
    var_NCCL_IB_HCA="=mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_14,mlx5_15,mlx5_16,mlx5_17,mlx5_9,mlx5_10,mlx5_11,mlx5_12"
  elif [ $shape == \"BM.GPU4.8\" ]
  then
    var_UCX_NET_DEVICES=mlx5_4:1
    var_NCCL_IB_HCA="=mlx5_0,mlx5_2,mlx5_6,mlx5_8,mlx5_10,mlx5_12,mlx5_14,mlx5_16,mlx5_1,mlx5_3,mlx5_7,mlx5_9,mlx5_11,mlx5_13,mlx5_15,mlx5_17"
  elif [ $shape == \"BM.GPU.H100.8\" ]
  then
    var_UCX_NET_DEVICES=eth0
    var_NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_12,mlx5_13,mlx5_14,mlx5_15,mlx5_16,mlx5_17"
  elif [ $shape == \"BM.GPU.H200.8\" ] || [ $shape == \"BM.GPU.B200.8\" ] 
  then
    var_UCX_NET_DEVICES=eth0
    var_NCCL_IB_HCA="=mlx5_0,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_9,mlx5_10,mlx5_11"
  elif [ $shape == \"BM.GPU.B300.8\" ]
  then
    var_UCX_NET_DEVICES=eth0
    var_NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_11,mlx5_12,mlx5_13,mlx5_14,mlx5_16,mlx5_17,mlx5_18,mlx5_19,mlx5_20,mlx5_21"
  else
    echo "Use the appropriate nccl test run script for non A100/H100/H200/B200 nodes"
  fi

  if [ $shape == \"BM.GPU.B4.8\" ] || [ $shape == \"BM.GPU.A100-v2.8\" ] || [ $shape == \"BM.GPU4.8\" ]
  then
    mpirun --mca pml ucx \
    --bind-to numa \
    --mca coll ^hcoll \
    -x UCX_TLS=ud,self,sm \
    -x UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
    -x HCOLL_ENABLE_MCAST_ALL=0 \
    -x coll_hcoll_enable=0 \
    -x NCCL_ALGO=Ring \
    --np $np --rankfile $rankfile ${EXEC_CMD} -b1G -e10G -i$((1024*1024*1024*9)) -n $iter >>  $logfile

  elif [ $shape == \"BM.GPU.H100.8\" ] || [ $shape == \"BM.GPU.H200.8\" ] || [ $shape == \"BM.GPU.B200.8\" ] || [ $shape == \"BM.GPU.B300.8\" ]
  then
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
    --np $np --hostfile $hostfile  ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 >>  $logfile
  fi

  tail -n 32 $logfile

done


