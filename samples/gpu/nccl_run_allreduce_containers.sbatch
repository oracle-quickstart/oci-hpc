#!/bin/bash
#SBATCH --job-name=nccl-allreduce-slurm-containers
#SBATCH --nodes=2
#SBATCH --gpus-per-node=8 # --gpus-per-node=4 on GB shape
#SBATCH --ntasks-per-node=8 # --ntasks-per-node=4 on GB shape
#SBATCH --exclusive



mkdir "$SLURM_JOB_ID" || exit 1
cd "$SLURM_JOB_ID" || exit 1

# Select the image-built MPI from the image manifest.
openmpi_version="$(yq e '.verified_components.openmpi.version' /etc/manifest.yaml)" || {
    echo "Cannot read the image MPI version from /etc/manifest.yaml; check the manifest and yq installation." >&2
    exit 1
}
if [[ -z "$openmpi_version" || "$openmpi_version" == "null" ]]; then
    echo "The image manifest does not record an Open MPI version." >&2
    exit 1
fi
openmpi_dir="/opt/openmpi-${openmpi_version#v}"
mpivars="${openmpi_dir}/bin/mpivars.sh"
if [[ ! -f "$mpivars" ]]; then
    echo "Image-provided MPI environment not found: $mpivars" >&2
    exit 1
fi

export NCCL_DEBUG=WARN
var_NCCL_TOPO_FILE=""

shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/shape)
rdma_planes=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/host/rdmaFabricData/planes 2>/dev/null || true)
if ! [[ "$rdma_planes" =~ ^[0-9]+$ ]]; then
    rdma_planes=1
fi

# Match nccl.conf and healthchecks; B300/B300.HS and GB300 multi-plane default to SPCX.
# USE_SPCX unset keeps the shape default; 0 selects Internal, 1 selects SPCX.
plugin=none
case "$shape" in
    BM.GPU.GB200.4|BM.GPU.GB200-v2.4|BM.GPU.GB200-v3.4) plugin=sharp ;;
    BM.GPU.B300.8|BM.GPU.B300.HS.8)
        if [[ "$rdma_planes" -gt 1 ]]; then plugin=spcx; fi ;;
    BM.GPU.GB300.4)
        if [[ "$rdma_planes" -gt 1 ]]; then plugin=spcx; else plugin=sharp; fi ;;
esac
case "${USE_SPCX-}" in
    "") ;;
    0) plugin=none ;;
    1) plugin=spcx ;;
    *) echo "USE_SPCX must be 0 or 1 when set." >&2; exit 1 ;;
esac
export NCCL_NET_PLUGIN=none
plugin_lib=""
if [[ "$plugin" != "none" ]]; then
    if [[ "$plugin" == "spcx" ]]; then
        plugins=(/opt/hpcx-*/nccl_spectrum-x_plugin/lib/libnccl-net-spcx.so)
    else
        plugins=(/opt/hpcx-*/nccl_rdma_sharp_plugin/lib/libnccl-net.so)
    fi
    if [[ ${#plugins[@]} -ne 1 || ! -f "${plugins[0]}" ]]; then
        echo "Expected one HPC-X $plugin plugin under /opt (USE_SPCX=0 selects native NCCL)." >&2
        exit 1
    fi
    plugin_lib="${plugins[0]%/*}"
    export NCCL_NET_PLUGIN="${plugins[0]}"
    # Mount only the selected package; do not initialize HPC-X MPI.
fi
plugin_mount=""
if [[ -n "$plugin_lib" ]]; then
    plugin_root="${plugin_lib%/*/*}"
    plugin_mount=",$plugin_root:$plugin_root:ro"
fi

# MPI coordinates ranks over shared memory/TCP; NCCL owns GPU/RDMA traffic.
export OMPI_MCA_pml=ob1 OMPI_MCA_btl=self,sm,tcp
export OMPI_MCA_btl_tcp_if_include=eth0 OMPI_MCA_coll=^ucc,hcoll
export NCCL_SOCKET_IFNAME=eth0

# default for BM.GPU.H100.8, BM.GPU.H200.8, BM.GPU.B200.8, BM.GPU.B300.8, BM.GPU.B300.HS.8
var_NCCL_IB_QPS_PER_CONNECTION=1
NCCL_ADAPTIVE_ROUTING_ARGS=()

if [ "$shape" == "BM.GPU.B4.8" ] || [ "$shape" == "BM.GPU.A100-v2.8" ]
then
  var_NCCL_IB_QPS_PER_CONNECTION=4
  var_NCCL_IB_HCA="=mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_14,mlx5_15,mlx5_16,mlx5_17,mlx5_9,mlx5_10,mlx5_11,mlx5_12"
elif [ "$shape" == "BM.GPU4.8" ]
then
  var_NCCL_IB_QPS_PER_CONNECTION=4
  var_NCCL_IB_HCA="=mlx5_0,mlx5_2,mlx5_6,mlx5_8,mlx5_10,mlx5_12,mlx5_14,mlx5_16,mlx5_1,mlx5_3,mlx5_7,mlx5_9,mlx5_11,mlx5_13,mlx5_15,mlx5_17"
elif [ "$shape" == "BM.GPU.H100.8" ]
then
  var_NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_12,mlx5_13,mlx5_14,mlx5_15,mlx5_16,mlx5_17"
elif [ "$shape" == "BM.GPU.H200.8" ] || [ "$shape" == "BM.GPU.B200.8" ]
then
  var_NCCL_IB_HCA="=mlx5_0,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_9,mlx5_10,mlx5_11"
elif { [ "$shape" == "BM.GPU.B300.8" ] || [ "$shape" == "BM.GPU.B300.HS.8" ]; } && [ "$rdma_planes" -gt 1 ]
then
  var_NCCL_IB_HCA="=rdma_vf_rail0,rdma_vf_rail1,rdma_vf_rail2,rdma_vf_rail3,rdma_vf_rail4,rdma_vf_rail5,rdma_vf_rail6,rdma_vf_rail7"
  var_NCCL_TOPO_FILE="/opt/oci-hpc/healthchecks/B300MP.xml"
  var_NCCL_IB_QPS_PER_CONNECTION=4
  NCCL_ADAPTIVE_ROUTING_ARGS=(NCCL_IB_ADAPTIVE_ROUTING=1)
elif [ "$shape" == "BM.GPU.B300.8" ] || [ "$shape" == "BM.GPU.B300.HS.8" ]
then
  var_NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_11,mlx5_12,mlx5_13,mlx5_14,mlx5_16,mlx5_17,mlx5_18,mlx5_19,mlx5_20,mlx5_21"
elif [ "$shape" == "BM.GPU.RTXPRO.8" ]
then
  var_NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_6,mlx5_7,mlx5_8,mlx5_9"
elif [[ "$shape" == "BM.GPU.GB200.4" || "$shape" == "BM.GPU.GB200-v2.4" ]]; then
  var_NCCL_IB_QPS_PER_CONNECTION=1
elif [[ "$shape" == "BM.GPU.GB300.4" && "$rdma_planes" -gt 1 ]]; then
  var_NCCL_IB_QPS_PER_CONNECTION=16
elif [[ "$shape" == "BM.GPU.GB200-v3.4" || "$shape" == "BM.GPU.GB300.4" ]]; then
  var_NCCL_IB_QPS_PER_CONNECTION=4
else
  echo "Unsupported shape: $shape" >&2
  exit 1
fi

if [ -n "${var_NCCL_TOPO_FILE}" ]; then
  export NCCL_TOPO_FILE="${var_NCCL_TOPO_FILE}"
fi

if [ "$shape" == "BM.GPU.B4.8" ] || [ "$shape" == "BM.GPU.A100-v2.8" ] || [ "$shape" == "BM.GPU4.8" ]
then
  export NCCL_DEBUG=WARN \
         NCCL_IB_SL=0 \
         NCCL_IB_TC=41 \
         NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
         NCCL_IB_GID_INDEX=3 \
         NCCL_ALGO=Ring \
         NCCL_IB_HCA="${var_NCCL_IB_HCA}" 

elif [ "$shape" == "BM.GPU.H100.8" ] || [ "$shape" == "BM.GPU.H200.8" ] || [ "$shape" == "BM.GPU.B200.8" ] || [ "$shape" == "BM.GPU.B300.8" ] || [ "$shape" == "BM.GPU.B300.HS.8" ] || [ "$shape" == "BM.GPU.RTXPRO.8" ]
then
  export NCCL_DEBUG=WARN \
         NCCL_CUMEM_ENABLE=0 \
         NCCL_IB_SPLIT_DATA_ON_QPS=0 \
         NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
         "${NCCL_ADAPTIVE_ROUTING_ARGS[@]}" \
         NCCL_IB_GID_INDEX=3 \
         NCCL_IB_TC=41 \
         NCCL_IB_SL=0 \
         NCCL_IB_TIMEOUT=22 \
         NCCL_IGNORE_CPU_AFFINITY=1 \
         NCCL_IB_HCA="${var_NCCL_IB_HCA}"

elif [[ "$shape" == "BM.GPU.GB200.4" || "$shape" == "BM.GPU.GB200-v2.4" ]]
then
export NCCL_DEBUG=WARN \
  NCCL_MNNVL_ENABLE=1 \
  NCCL_CUMEM_ENABLE=1 \
  NCCL_IB_HCA=mlx5_0,mlx5_1,mlx5_3,mlx5_4 \
  NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
  NCCL_NVLS_ENABLE=1 \
  NCCL_NET_GDR_C2C=1

elif [ "$shape" == "BM.GPU.GB300.4" ] && [ "$rdma_planes" -gt 1 ]
then
export NCCL_IB_HCA=rdma_vf_rail0,rdma_vf_rail1,rdma_vf_rail2,rdma_vf_rail3 \
  NCCL_ASYNC_ERROR_HANDLING=1 \
  NCCL_IB_TIMEOUT=16 \
  NCCL_IB_RETRY_CNT=7 \
  NCCL_IB_SL=0 \
  NCCL_IB_TC=96 \
  NCCL_IB_GID_INDEX=3 \
  NCCL_NVLS_ENABLE=1 \
  NCCL_MNNVL_ENABLE=1 \
  NCCL_WORK_FIFO_BYTES=0 \
  NCCL_NET_GDR_C2C=1 \
  NCCL_CUMEM_ENABLE=1 \
  NCCL_IGNORE_CPU_AFFINITY=1 \
  NCCL_IB_ADAPTIVE_ROUTING=1 \
  NCCL_IB_SPLIT_DATA_ON_QPS=0 \
  NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
  NCCL_TOPO_FILE=${NCCL_TOPO_FILE:-/opt/oci-hpc/healthchecks/GB300MP.xml}

elif [[ "$shape" == "BM.GPU.GB200-v3.4" ]] || { [[ "$shape" == "BM.GPU.GB300.4" ]] && [[ "$rdma_planes" -le 1 ]]; }
then
export NCCL_DEBUG=WARN \
  NCCL_MNNVL_ENABLE=1 \
  NCCL_CUMEM_ENABLE=1 \
  NCCL_IB_HCA="=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8" \
  NCCL_NVLS_ENABLE=1 \
  NCCL_NET_GDR_C2C=1 \
  NCCL_IB_GID_INDEX=3 \
  NCCL_IB_TC=41 \
  NCCL_IB_SL=0 \
  NCCL_IB_TIMEOUT=22 \
  NCCL_BUFFSIZE=16777216 \
  NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
  NCCL_IB_SPLIT_DATA_ON_QPS=0 \
  NCCL_NET_GDR_C2C=1 \
  NCCL_DMABUF_ENABLE=1
fi

env | grep "SLURMD_NODENAME="
USER=`whoami`

# Pull with, for example:
# ENROOT_MAX_PROCESSORS=64
# enroot import -o nvidia+cuda-dl-base+26.05-cuda13.2-devel-ubuntu24.04.sqsh 'docker://nvcr.io#nvidia/cuda-dl-base:26.05-cuda13.2-devel-ubuntu24.04'
CONTAINER_IMAGE="${CONTAINER_IMAGE:-/home/ubuntu/nvidia+cuda-dl-base+26.05-cuda13.2-devel-ubuntu24.04.sqsh}"
# The container must provide compatible CUDA, NCCL, verbs and system libraries for
# the host-built MPI/tests and selected network plugin. Do not mount host CUDA over it.
# Check ldd on the mounted benchmark inside the chosen container before testing.
CONTAINER_MOUNTS="/opt/oci-hpc:/opt/oci-hpc:ro,$openmpi_dir:$openmpi_dir:ro$plugin_mount"

# Legacy images used /opt/oci-hpc/nccl-test/build.
EXEC_CMD="/opt/oci-hpc/nccl-tests/bin/${EXEC:-all_reduce_perf}"
if [[ ! -x "$EXEC_CMD" ]]; then
    echo "Image-provided NCCL benchmark not found: $EXEC_CMD" >&2
    exit 1
fi

export PMIX_MCA_psec=native
export PMIX_MCA_gds=hash

# Pyxis otherwise gives existing container-image variables precedence.
container_env=$(compgen -e | grep -E '^(NCCL_|OMPI_MCA_|PMIX_MCA_)' | paste -sd, -)

srun --mpi=pmix --gpus-per-node=$SLURM_GPUS_PER_NODE \
     --cpu-bind=ldoms \
     --ntasks=$((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) \
     --ntasks-per-node=$SLURM_NTASKS_PER_NODE \
     --container-image="$CONTAINER_IMAGE" \
     --container-mounts="$CONTAINER_MOUNTS" \
     --container-env="$container_env" \
     bash -c '
       source "$1" || exit 1
       if [[ -n "$2" ]]; then
           export LD_LIBRARY_PATH="$2${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
       fi
       exec "$3" -b 1G -e 16G -f 2 -g 1 -n 50
     ' bash "$mpivars" "$plugin_lib" "$EXEC_CMD"
