#!/bin/bash
#SBATCH --job-name=nccl
#SBATCH --nodes=2
#SBATCH --gpus-per-node=8
#SBATCH --ntasks-per-node=8
#SBATCH --exclusive
export PMI_DEBUG=1

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

cd /nfs/cluster
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID

MACHINEFILE="hostfile"
ORDEREDMACHINEFILE="ordered_hostfile_system_name"
ORDEREDRANKMACHINEFILE="rankfile_system_name"
NODE_SWITCH_LIST="node_switch_list"

scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE
echo MACHINEFILE
cat $MACHINEFILE

source /etc/os-release
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then
    python3 /home/opc/node_ordering_by_rack.py --input_file $MACHINEFILE > /dev/null
elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then
    python3 /home/ubuntu/node_ordering_by_rack.py --input_file $MACHINEFILE > /dev/null
fi


echo ORDEREDRANKMACHINEFILE
cat $ORDEREDRANKMACHINEFILE
echo NODE_SWITCH_LIST
cat $NODE_SWITCH_LIST

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

export NCCL_DEBUG=WARN


shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ $shape == \"BM.GPU.H100.8\" ]
then
  var_UCX_NET_DEVICES=eth0
  var_NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_12,mlx5_13,mlx5_14,mlx5_15,mlx5_16,mlx5_17"
elif [ $shape == \"BM.GPU.H200.8\" ]
then
  var_UCX_NET_DEVICES=eth0
  var_NCCL_IB_HCA="=mlx5_0,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_9,mlx5_10,mlx5_11"
else
  echo "Use the appropriate nccl test run script for non H100/H200 nodes"
fi

echo "Running ${EXEC_CMD} test on ${SLURM_NNODES} nodes"


mpirun --mca pml ucx \
  --bind-to numa \
  --mca coll ^hcoll \
  -x NCCL_DEBUG=WARN \
  -x NCCL_CUMEM_ENABLE=0 \
  -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
  -x NCCL_IB_QPS_PER_CONNECTION=1 \
  -x NCCL_IB_GID_INDEX=3 \
  -x NCCL_IB_TC=41 \
  -x NCCL_IB_SL=0 \
  -x NCCL_IB_TIMEOUT=22 \
  -x NCCL_NET_PLUGIN=${hpcx_path} \
  -x HCOLL_ENABLE_MCAST_ALL=0 \
  -x coll_hcoll_enable=0 \
  -x UCX_TLS=tcp \
  -x UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
  -x RX_QUEUE_LEN=8192 \
  -x IB_RX_QUEUE_LEN=8192 \
  -x NCCL_SOCKET_IFNAME=${var_UCX_NET_DEVICES} \
  -x NCCL_IGNORE_CPU_AFFINITY=1 \
  -x NCCL_IB_HCA="${var_NCCL_IB_HCA}" \
  --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --rankfile $ORDEREDRANKMACHINEFILE ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50
