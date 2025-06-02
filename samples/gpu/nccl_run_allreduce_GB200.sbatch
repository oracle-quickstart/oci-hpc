#!/bin/bash
#SBATCH --job-name=nccl-allreduce-slurm
#SBATCH --nodes=2
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
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

cd
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
    python3 /home/opc/node_ordering_by_rack.py --input_file $MACHINEFILE --gpus 4 > /dev/null
elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then
    python3 /home/ubuntu/node_ordering_by_rack.py --input_file $MACHINEFILE --gpus 4 > /dev/null
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

echo "Running ${EXEC_CMD} test on ${SLURM_NNODES} nodes"
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