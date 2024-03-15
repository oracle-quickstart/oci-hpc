#!/bin/bash
#SBATCH --job-name=nccl-allreduce-slurm-containers
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

MPIVARS_PATH=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`

if [[ "$MPIVARS_PATH" == "" ]]; then
    MPIVARS_PATH=`ls /opt/openmpi-*/bin/mpivars.sh`
fi

if [[ "$MPIVARS_PATH" == "" ]]; then
    echo "Could not find MPIPATH"; exit; fi

source $MPIVARS_PATH
LOCAL_MPI=${MPIVARS_PATH%/*}

shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ $shape == \"BM.GPU.H100.8\" ]
then
  var_UCX_NET_DEVICES=eth0
else
  echo "Use the appropriate nccl test run script for non H100 nodes"
fi

export NCCL_CROSS_NIC=0 \
       NCCL_SOCKET_NTHREADS=16 \
       NCCL_DEBUG=WARN \
       NCCL_CUMEM_ENABLE=0 \
       NCCL_IB_SPLIT_DATA_ON_QPS=0 \
       NCCL_IB_QPS_PER_CONNECTION=16 \
       NCCL_IB_GID_INDEX=3 \
       NCCL_IB_TC=41 \
       NCCL_IB_SL=0 \
       NCCL_IB_TIMEOUT=22 \
       NCCL_NET_PLUGIN=none \
       NCCL_SOCKET_IFNAME=eth0 \
       NCCL_IGNORE_CPU_AFFINITY=1 \
       NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_12,mlx5_13,mlx5_14,mlx5_15,mlx5_16,mlx5_17" \
       NCCL_TOPO_FILE=/nfs/cluster/H100-topology.xml \
       HCOLL_ENABLE_MCAST_ALL=0 \
       coll_hcoll_enable=0 \
       UCX_TLS=tcp \
       UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
       RX_QUEUE_LEN=8192 \
       IB_RX_QUEUE_LEN=8192 \
       OMPI_MCA_coll=^hcoll

env | grep "SLURMD_NODENAME="
USER=`whoami`

CONTAINER_IMAGE="/home/ubuntu/nvcr.io+nvidia+pytorch+24.01-py3.sqsh"
CONTAINER_MOUNTS="/opt/oci-hpc/nccl-test:/nccl,$LOCAL_MPI:$LOCAL_MPI,/nfs/cluster:/nfs/cluster"
echo $LOCAL_MPI
echo $MPIVARS_PATH

srun --mpi=pmi2 --gpus-per-node=$SBATCH_GPUS_PER_NODE \
     --ntasks-per-node=$SLURM_NTASKS_PER_NODE \
     --container-image=$CONTAINER_IMAGE \
     --container-mounts=$CONTAINER_MOUNTS \
     bash -c "
     source $MPIVARS_PATH &&
     /nccl/build/all_reduce_perf -b 1G -e 16G -f 2 -g 1
     "