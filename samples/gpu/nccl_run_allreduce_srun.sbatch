#!/bin/bash
#SBATCH --job-name=nccl-allreduce-srun
#SBATCH --nodes=2
#SBATCH --gpus-per-node=8
#SBATCH --ntasks-per-node=8
#SBATCH --exclusive
export PMI_DEBUG=1


cd /nfs/scratch
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID

MACHINEFILE="hostfile"

scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE
echo INPUTFILE
cat $MACHINEFILE

mpivars_path=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`

if [[ "$mpivars_path" == "" ]]; then
    mpivars_path=`ls /opt/openmpi-*/bin/mpivars.sh`
fi

if [[ "$mpivars_path" == "" ]]; then
    echo "Could not find MPIPATH"; exit; fi

source $mpivars_path
echo $mpivars_path

shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ $shape == \"BM.GPU.B4.8\" ] || [ $shape == \"BM.GPU.A100-v2.8\" ]
then
  var_UCX_NET_DEVICES=mlx5_0:1
  var_NCCL_IB_HCA="=mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_14,mlx5_15,mlx5_16,mlx5_17,mlx5_9,mlx5_10,mlx5_11,mlx5_12"
elif [ $shape == \"BM.GPU4.8\" ]
then
  var_UCX_NET_DEVICES=mlx5_4:1
  var_NCCL_IB_HCA="=mlx5_0,mlx5_2,mlx5_6,mlx5_8,mlx5_10,mlx5_12,mlx5_14,mlx5_16,mlx5_1,mlx5_3,mlx5_7,mlx5_9,mlx5_11,mlx5_13,mlx5_15,mlx5_17"
fi

export NCCL_DEBUG=WARN \
  OMPI_MCA_coll=^hcoll \
  RX_QUEUE_LEN=8192 \
  IB_RX_QUEUE_LEN=8192 \
  NCCL_IGNORE_CPU_AFFINITY=1 \
  NCCL_IB_SL=0 \
  NCCL_IB_TC=41 \
  NCCL_IB_QPS_PER_CONNECTION=4 \
  UCX_TLS=ud,self,sm \
  UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
  HCOLL_ENABLE_MCAST_ALL=0 \
  coll_hcoll_enable=0 \
  NCCL_IB_GID_INDEX=3 \
  NCCL_ALGO=Ring \
  NCCL_IB_HCA="${var_NCCL_IB_HCA}"
  srun --mpi=pmix_v3 --gpus-per-node=$SLURM_GPUS_PER_NODE --ntasks-per-node=$SLURM_NTASKS_PER_NODE /opt/oci-hpc/nccl-test/build/all_reduce_perf -b1G -e10G -i$((1024*1024*1024*9)) -n 100
