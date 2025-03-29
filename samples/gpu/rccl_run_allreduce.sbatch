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

var_NCCL_IB_HCA="=mlx5_0,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_7,mlx5_8,mlx5_9"


  mpirun --mca pml ucx \
  --bind-to numa \
-x UCX_NET_DEVICES=mlx5_0:1 \
-x NCCL_SOCKET_IFNAME=eth0 \
-x NCCL_IB_SL=0 \
-x NCCL_IB_HCA="=mlx5_0,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_7,mlx5_8,mlx5_9" \
-x coll_hcoll_enable=0 \
-x HCOLL_ENABLE_MCAST_ALL=0 \
-x NCCL_IGNORE_CPU_AFFINITY=1 \
-x NCCL_IB_QPS_PER_CONNECTION=4 \
-x RX_QUEUE_LEN=8192 \
-x IB_RX_QUEUE_LEN=8192 \
-np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --hostfile $MACHINEFILE  /opt/rccl-tests/build/all_reduce_perf -b 1G -e 16G -f 2 -g 1