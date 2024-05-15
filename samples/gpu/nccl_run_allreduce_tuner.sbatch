#!/bin/bash
#SBATCH --job-name=nccl-allreduce-slurm
#SBATCH --nodes=2
#SBATCH --gpus-per-node=8
#SBATCH --ntasks-per-node=8
#SBATCH --exclusive
export PMI_DEBUG=1


cd /nfs/scratch
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID

MACHINEFILE="hostfile"
ORDEREDMACHINEFILE="ordered_hostfile_system_name"
ORDEREDRANKMACHINEFILE="rankfile_system_name"

scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE
echo MACHINEFILE
cat $MACHINEFILE

source /etc/os-release
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then
    python3 /home/opc/node_ordering_by_rack.py --input_file $MACHINEFILE > /dev/null
elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then
    python3 /home/ubuntu/node_ordering_by_rack.py --input_file $MACHINEFILE > /dev/null
fi


echo ORDEREDMACHINEFILE
cat $ORDEREDMACHINEFILE
echo ORDEREDRANKMACHINEFILE
cat $ORDEREDRANKMACHINEFILE

mpivars_path=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`

if [[ "$mpivars_path" == "" ]]; then
    mpivars_path=`ls /opt/openmpi-*/bin/mpivars.sh`
fi

if [[ "$mpivars_path" == "" ]]; then
    echo "Could not find MPIPATH"; exit; fi

source $mpivars_path

export NCCL_DEBUG=WARN

#mpirun -d --mca pml ucx -x SLURM_JOB_NODELIST=$host_list --bind-to numa  -x NCCL_DEBUG=WARN  -x NCCL_IB_SL=0 -x NCCL_IB_TC=41 -x NCCL_IB_QPS_PER_CONNECTION=4 -x NCCL_IB_GID_INDEX=3 -x NCCL_ALGO=Ring -x NCCL_TOPO_FILE=/home/opc/topo-flattened-b4.xml -x NCCL_IB_HCA="mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_11,mlx5_12,mlx5_13,mlx5_16,mlx5_17,mlx5_18,mlx5_19"   -x UCX_NET_DEVICES=mlx5_0:1 -x HCOLL_ENABLE_MCAST_ALL=0 -x coll_hcoll_enable=0 -x UCX_TLS=ud,self,sm  -np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --rankfile rankfile_system_name  /home/opc/nccl-tests/build/all_reduce_perf -b1G -e10G -i$((1024*1024*1024*9))  -n 100
# no need to pass:  -x SLURM_JOB_NODELIST=$host_list

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

NCCL_version=`sudo ldconfig -v 2>&1 | grep "libnccl.so" | tail -n1 | sed -r 's/^.*\.so\.//'`
arr_NCCL=(${NCCL_version//./ })
if [ ${arr_NCCL[2]} > 20 ]
then
  tuner_path=/opt/oci-hpc/oci-tuner/libnccl-ocituner-A100.so.2.0.1
else
  tuner_path=/opt/oci-hpc/oci-tuner/libnccl-ocituner-A100.so.1.0.2
fi


  mpirun --mca pml ucx \
  --bind-to numa \
  --mca coll ^hcoll \
  -x NCCL_DEBUG=WARN \
  -x NCCL_IB_SL=0 \
  -x NCCL_IB_TC=41 \
  -x NCCL_IB_QPS_PER_CONNECTION=4 \
  -x UCX_TLS=ud,self,sm \
  -x UCX_NET_DEVICES=${var_UCX_NET_DEVICES} \
  -x HCOLL_ENABLE_MCAST_ALL=0 \
  -x coll_hcoll_enable=0 \
  -x NCCL_IB_GID_INDEX=3 \
  -x NCCL_TUNER_PLUGIN=${tuner_path} \
  -x NCCL_IB_HCA="${var_NCCL_IB_HCA}" \
  --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE))  --rankfile $ORDEREDRANKMACHINEFILE  /opt/oci-hpc/nccl-test/build/all_reduce_perf -b1G -e10G -i$((1024*1024*1024*9)) -n 100


