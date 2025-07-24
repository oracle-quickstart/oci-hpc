#!/bin/bash
#SBATCH --job-name=nccl-container
#SBATCH --nodes=2
#SBATCH --gpus-per-node=8
#SBATCH --ntasks-per-node=8
#SBATCH --exclusive

# This script defaults to running all_reduce_perf, but can run other NCCL tests if launched with
# EXEC=all_gather_perf sbatch -N8 ./nccl_run_allreduce_containers_H100_200.sbatch

#Here is an example of how you might build the NCCL tests inside of a pytorch container for use with this script:
#
##!/bin/bash
##SBATCH --output=%x.%J.%N.out
#
#export VERSION=24.11
#CONT="/nfs/cluster/sce/ngc/pytorch_$VERSION.sqsh"
#MOUNT="/nfs/cluster/sce/nccl:/nccl,/nfs/cluster/sce/mpi/hpcx-v2.22-gcc-doca_ofed-ubuntu22.04-cuda12-x86_64:/mpi/hpcx"
#
#srun --ntasks=$SLURM_JOB_NUM_NODES \
#    --container-image "${CONT}" \
#    --container-name=nccl \
#    --container-mounts="${MOUNT}" \
#    --ntasks-per-node=1 \
#    bash -c 'cd /nccl && git clone https://github.com/NVIDIA/nccl-tests.git && source /mpi/hpcx/hpcx-init.sh && hpcx_load && cd nccl-tests && make MPI=1 && mv ../nccl-tests ../nccl-tests-${VERSION}'
#


# Set to the pytorch container version you want to use
export PYTORCH_VERSION=24.11

# Set to where the pytorch container .sqsh can be found
IMAGE_PATH="/nfs/cluster/sce/ngc/"

# Assuming the nccl_tests to run inside of the container are located outside of the container, specify their location here
NCCL_TEST_PATH="/nfs/cluster/sce/nccl/nccl-tests-${PYTORCH_VERSION}"

# Set to the path to the test executables within the container, imacted by mount point chosen for NCCL_TEST_PATH in CONTAINER_MOUNTS below
NCCL_TEST_CONTAINER_PATH="/nccl/build/"

MPIVARS_PATH=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`

if [[ "$MPIVARS_PATH" == "" ]]; then
    MPIVARS_PATH=`ls /opt/openmpi-*/bin/mpivars.sh`
fi

if [[ "$MPIVARS_PATH" == "" ]]; then
    echo "Could not find MPIPATH"; exit; fi

source $MPIVARS_PATH
LOCAL_MPI=${MPIVARS_PATH%/*}

hpcx_path=`ls /opt/hpcx-*/nccl_rdma_sharp_plugin/lib/libnccl-net.so`
if [[ "$hpcx_path" == "" ]]; then
    hpcx_path=none
fi

CONTAINER_IMAGE="${IMAGE_PATH}/pytorch_${PYTORCH_VERSION}.sqsh"
CONTAINER_MOUNTS="${NCCL_TEST_PATH}:/nccl,$LOCAL_MPI:$LOCAL_MPI,/nfs/cluster:/nfs/cluster"

if [[ -z "${EXEC}" ]]; then
  export EXEC_CMD="${NCCL_TEST_CONTAINER_PATH}/all_reduce_perf"
else
  export EXEC_CMD="${NCCL_TEST_CONTAINER_PATH}/${EXEC}"
fi

cd /nfs/cluster/
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID

MACHINEFILE="hostfile"
ORDEREDMACHINEFILE="ordered_hostfile_system_name"
ORDEREDMACHINEFILENTIMES="ordered_hostfile_system_name_n_times"
ORDEREDRANKMACHINEFILE="rankfile_system_name"
NODE_SWITCH_LIST="node_switch_list"

scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE

source /etc/os-release
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then
    python3 /home/opc/node_ordering_by_rack.py --input_file $MACHINEFILE > /dev/null
elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then
    python3 /home/ubuntu/node_ordering_by_rack.py --input_file $MACHINEFILE > /dev/null
fi


for node in $(cat $ORDEREDMACHINEFILE) ; do
        for x in $(seq 1 $SLURM_NTASKS_PER_NODE) ; do
                echo $node >> $ORDEREDMACHINEFILENTIMES
        done
done

export PMI_DEBUG=1

echo ORDEREDMACHINEFILENTIMES
cat $ORDEREDMACHINEFILENTIMES
echo NODE_SWITCH_LIST
cat $NODE_SWITCH_LIST


shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`

if [ $shape == \"BM.GPU.H100.8\" ]
then
  var_UCX_NET_DEVICES=eth0
  var_NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_12,mlx5_13,mlx5_14,mlx5_15,mlx5_16,mlx5_17"
elif [ $shape == \"BM.GPU.H200.8\" ] || [ $shape == \"BM.GPU.B200.8\" ]
then
  var_UCX_NET_DEVICES=eth0
  var_NCCL_IB_HCA="=mlx5_0,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_9,mlx5_10,mlx5_11"
else
  echo "Use the appropriate nccl test run script for non H100/H200 nodes"
fi

export RX_QUEUE_LEN=8192 \
       IB_RX_QUEUE_LEN=8192 \
       NCCL_IB_TIMEOUT=22 \
       NCCL_IB_SL=0 \
       NCCL_IB_TC=41 \
       NCCL_IGNORE_CPU_AFFINITY=1 \
       NCCL_IB_GID_INDEX=3 \
       NCCL_IB_SPLIT_DATA_ON_QPS=0 \
       NCCL_IB_QPS_PER_CONNECTION=1 \
       HCOLL_ENABLE_MCAST_ALL=0 \
       coll_hcoll_enable=0 \
       UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
       NCCL_IB_HCA="${var_NCCL_IB_HCA}" \
       NCCL_NET_PLUGIN=${hpcx_path} \
       NCCL_SOCKET_IFNAME=${var_UCX_NET_DEVICES} \
       UCX_TLS=tcp \
       NCCL_CUMEM_ENABLE=0 \
       NCCL_DEBUG=WARN \
       OMPI_MCA_coll=^hcoll

echo "Running ${EXEC_CMD} test on ${SLURM_NNODES} nodes using container pytorch ${PYTORCH_VERSION}"

export SLURM_HOSTFILE=$ORDEREDMACHINEFILENTIMES

srun --mpi=pmi2 --gpus-per-node=$SBATCH_GPUS_PER_NODE \
     --ntasks-per-node=$SLURM_NTASKS_PER_NODE \
     --container-image=$CONTAINER_IMAGE \
     --container-mounts=$CONTAINER_MOUNTS \
     bash -c "
     source $MPIVARS_PATH &&
     ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50
     "
