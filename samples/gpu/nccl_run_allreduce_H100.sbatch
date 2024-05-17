#!/bin/bash
#SBATCH --job-name=nccl-allreduce-slurm
#SBATCH --nodes=2
#SBATCH --gpus-per-node=8
#SBATCH --ntasks-per-node=8
#SBATCH --exclusive
export PMI_DEBUG=1


cd /nfs/cluster
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID

MACHINEFILE="hostfile"

scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE
echo MACHINEFILE
cat $MACHINEFILE

source /etc/os-release

mpivars_path=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`

if [[ "$mpivars_path" == "" ]]; then
    mpivars_path=`ls /opt/openmpi-*/bin/mpivars.sh`
fi

if [[ "$mpivars_path" == "" ]]; then
    echo "Could not find MPIPATH"; exit; fi

source $mpivars_path

shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
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
  -x NCCL_SOCKET_IFNAME=${var_UCX_NET_DEVICES} \
  -x NCCL_IGNORE_CPU_AFFINITY=1 \
  -x NCCL_IB_HCA="${var_NCCL_IB_HCA}" \
  --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --hostfile $MACHINEFILE  /opt/oci-hpc/nccl-test/build/all_reduce_perf -b 1G -e 16G -f 2 -g 1

  # If NCCL version is lower than 2.20.3, it is recommended to use the topology filefor optimal performances 
  # -x NCCL_TOPO_FILE=~/H100-topology.xml \

  # If NCCL version is lower than 2.20.3, it is recommended to use 
  # -x NCCL_CROSS_NIC=0 for multiple subnets and large scale jobs (>16 nodes)
  # -x NCCL_CROSS_NIC=1 for single subnets and small scale jobs (<16 nodes)
  
  # If NCCL version is higher than 2.20.3, the absolute max NCCL throughput at large message size will be obtained with
  # -x NCCL_MIN_NCHANNELS=32 \ But it does take some processing power away from the GPU for networking gains and is not recommended while running jobs. 