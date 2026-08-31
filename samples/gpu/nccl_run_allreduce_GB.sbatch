#!/bin/bash
#SBATCH --job-name=nccl-allreduce-slurm
#SBATCH --nodes=2
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --exclusive
export PMI_DEBUG=1

# This script defaults to running all_reduce_perf, but can run other NCCL tests if launched with
# EXEC=all_gather_perf sbatch -N8 ./nccl_run_allreduce_GB200.sbatch

if [[ -z "${EXEC}" ]]; then
  export EXEC_CMD="/opt/oci-hpc/nccl-test/build/all_reduce_perf"
else
  export EXEC_CMD="/opt/oci-hpc/nccl-test/build/${EXEC}"
fi

if [ ! -f ${EXEC_CMD} ]; then
    echo "Test executable ${EXEC_CMD} not found!"
    exit 1
fi

cd
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID

MACHINEFILE="hostfile"
ORDEREDMACHINEFILE="ordered_hostfile"
ORDEREDRANKMACHINEFILE="ordered_rankfile"
NODE_SWITCH_LIST="node_switch_list"

scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE
echo MACHINEFILE
cat $MACHINEFILE

/opt/oci-hpc/bin/node_ordering_by_rack.py --gpus 4 --input_file $MACHINEFILE > /dev/null

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

echo "Running ${EXEC_CMD} test on ${SLURM_NNODES} nodes"
shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)
rdma_planes=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/host/rdmaFabricData/planes 2>/dev/null || true)
if ! [[ "$rdma_planes" =~ ^[0-9]+$ ]]; then
    rdma_planes=1
fi

if [ "$shape" == "BM.GPU.GB200.4" ]
then
mpirun --bind-to none \
        --mca coll ^hcoll \
        -x NCCL_DEBUG=WARN \
        -x NCCL_MNNVL_ENABLE=1 \
        -x NCCL_CUMEM_ENABLE=1 \
        -x NCCL_NET_PLUGIN=${hpcx_path} \
        -x UCX_NET_DEVICES=mlx5_0:1,mlx5_1:1,mlx5_3:1,mlx5_4:1 \
        -x NCCL_IB_HCA==mlx5_0,mlx5_1,mlx5_3,mlx5_4 \
        -x NCCL_NVLS_ENABLE=1 \
        -x NCCL_NET_GDR_C2C=1 \
        -x NCCL_SOCKET_IFNAME=eth0 \
        --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --rankfile $ORDEREDRANKMACHINEFILE ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50
elif [ "$shape" == "BM.GPU.GB300.4" ] && [ "$rdma_planes" -gt 1 ]
then
mpirun --bind-to numa \
        --mca pml ucx \
        --mca coll ^hcoll \
        -x LD_LIBRARY_PATH \
        -x UCX_NET_DEVICES=eth0 \
        -x RX_QUEUE_LEN=8192 \
        -x IB_RX_QUEUE_LEN=8192 \
        -x HCOLL_ENABLE_MCAST_ALL=0 \
        -x coll_hcoll_enable=0 \
        -x NCCL_SOCKET_IFNAME=eth0 \
        -x NCCL_IB_HCA=rdma_vf_rail0,rdma_vf_rail1,rdma_vf_rail2,rdma_vf_rail3 \
        -x NCCL_ASYNC_ERROR_HANDLING=1 \
        -x NCCL_IB_TIMEOUT=16 \
        -x NCCL_IB_RETRY_CNT=7 \
        -x NCCL_IB_SL=0 \
        -x NCCL_IB_TC=96 \
        -x NCCL_IB_GID_INDEX=3 \
        -x NCCL_NVLS_ENABLE=1 \
        -x NCCL_MNNVL_ENABLE=1 \
        -x NCCL_WORK_FIFO_BYTES=0 \
        -x NCCL_NET_GDR_C2C=1 \
        -x NCCL_CUMEM_ENABLE=1 \
        -x NCCL_IGNORE_CPU_AFFINITY=1 \
        -x NCCL_NET_PLUGIN=spcx \
        -x NCCL_NET=IB \
        -x NCCL_IB_ADAPTIVE_ROUTING=1 \
        -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
        -x NCCL_IB_QPS_PER_CONNECTION=16 \
        -x NCCL_TOPO_FILE=${NCCL_TOPO_FILE:-/opt/oci-hpc/healthchecks/GB300MP.xml} \
        --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --rankfile $ORDEREDRANKMACHINEFILE ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50
else
mpirun --bind-to numa \
        --mca pml ucx \
        --mca coll ^hcoll \
        -x NCCL_DEBUG=WARN \
        -x NCCL_MNNVL_ENABLE=1 \
        -x NCCL_CUMEM_ENABLE=1 \
        -x NCCL_NET_PLUGIN=none \
        -x UCX_NET_DEVICES=eth0 \
        -x NCCL_IB_HCA==mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8 \
        -x NCCL_NVLS_ENABLE=1 \
        -x NCCL_SOCKET_IFNAME=eth0 \
        -x NCCL_NET_GDR_C2C=1 \
        -x NCCL_IB_GID_INDEX=3 \
        -x NCCL_IB_TC=41 \
        -x NCCL_IB_SL=0 \
        -x NCCL_IB_TIMEOUT=22 \
        -x RX_QUEUE_LEN=8192 \
        -x IB_RX_QUEUE_LEN=8192 \
        -x HCOLL_ENABLE_MCAST_ALL=0 \
        -x coll_hcoll_enable=0 \
        -x NCCL_BUFFSIZE=16777216 \
        -x NCCL_IB_QPS_PER_CONNECTION=4 \
        -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
        -x NCCL_NET_GDR_C2C=1 \
        -x NCCL_DMABUF_ENABLE=1 \
        --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --rankfile $ORDEREDRANKMACHINEFILE ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50

fi
