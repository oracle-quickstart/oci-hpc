#!/bin/bash
#SBATCH --job-name=nccl-allreduce-slurm
#SBATCH --nodes=2
#SBATCH --gpus-per-node=8
#SBATCH --ntasks-per-node=8
#SBATCH --exclusive

inspector_mode=""
for arg in "$@"; do
  case "$arg" in
    --with-nccl-inspector-otel|--with-nccl-inspector-jsonl)
      if [[ -n "$inspector_mode" ]]; then
        echo "Choose only one NCCL Inspector mode" >&2
        exit 2
      fi
      inspector_mode="$arg"
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: sbatch nccl_run_allreduce.sbatch [--with-nccl-inspector-otel|--with-nccl-inspector-jsonl]" >&2
      exit 2
      ;;
  esac
done

inspector_mpirun_args=()
if [[ -n "$inspector_mode" ]]; then
  export NCCL_PROFILER_PLUGIN=libnccl-profiler-inspector.so
  export NCCL_INSPECTOR_ENABLE=1
  export NCCL_INSPECTOR_DUMP_THREAD_INTERVAL_MICROSECONDS=5000000
  export NCCL_INSPECTOR_DUMP_DIR="/config/metrics/nccl-inspector/job-${SLURM_JOB_ID}"
  mkdir -p "$NCCL_INSPECTOR_DUMP_DIR"
  inspector_mpirun_args+=( -x NCCL_PROFILER_PLUGIN -x NCCL_INSPECTOR_ENABLE
    -x NCCL_INSPECTOR_DUMP_THREAD_INTERVAL_MICROSECONDS -x NCCL_INSPECTOR_DUMP_DIR )
fi
if [[ "$inspector_mode" == "--with-nccl-inspector-otel" ]]; then
  export NCCL_INSPECTOR_OTEL_EXPORT=1
  export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:4318/v1/metrics
  inspector_mpirun_args+=( -x NCCL_INSPECTOR_OTEL_EXPORT -x OTEL_EXPORTER_OTLP_METRICS_ENDPOINT )
fi

# This script defaults to running all_reduce_perf, but can run other NCCL tests if launched with
# EXEC=all_gather_perf sbatch -N8 ./nccl_run_allreduce.sbatch

# On legacy images you may use /opt/oci-hpc/nccl-test/build instead; an updated HPC image is 
# highly recommended.
export EXEC_CMD="/opt/oci-hpc/nccl-tests/bin/${EXEC:-all_reduce_perf}"

if [ ! -f ${EXEC_CMD} ]; then
    echo "Test executable ${EXEC_CMD} not found!"
    exit 1
fi

cd
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID

# generate rankfile
RANKFILE="slurm.rankfile"
srun --mpi=pmix \
bash -c 'printf "%08d rank %d=%s slot=%d\n" \
    ${SLURM_PROCID} ${SLURM_PROCID} ${SLURMD_NODENAME} ${SLURM_LOCALID}' |
LC_ALL=C sort -n |
sed 's/^[0-9]* //' > ${RANKFILE}
echo RANKFILE
cat $RANKFILE

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
source "$mpivars" || exit 1

shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)
echo "shape is $shape"
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
        echo "Expected one HPC-X $plugin plugin under /opt/hpcx-* (USE_SPCX=0 selects native NCCL)." >&2
        exit 1
    fi
    plugin_lib="${plugins[0]%/*}"
    export NCCL_NET_PLUGIN="${plugins[0]}"
    export LD_LIBRARY_PATH="$plugin_lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

# MPI coordinates ranks over shared memory/TCP; NCCL owns GPU/RDMA traffic.
mpi_args=(--mca pml ob1 --mca btl self,sm,tcp
          --mca btl_tcp_if_include eth0 --mca coll ^ucc,hcoll
          -x NCCL_SOCKET_IFNAME=eth0
          -x NCCL_NET_PLUGIN -x LD_LIBRARY_PATH)

export NCCL_DEBUG=WARN
var_NCCL_TOPO_FILE=""

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
  NCCL_ADAPTIVE_ROUTING_ARGS=(-x NCCL_IB_ADAPTIVE_ROUTING=1)
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
  echo "Unsupported shape: $shape"
  exit 1 
fi

echo "Running ${EXEC_CMD} test on ${SLURM_NNODES} nodes"
NCCL_TOPO_ARGS=()
if [ -n "${var_NCCL_TOPO_FILE}" ]; then
  NCCL_TOPO_ARGS=(-x NCCL_TOPO_FILE="${var_NCCL_TOPO_FILE}")
fi

if [ "$shape" == "BM.GPU.B4.8" ] || [ "$shape" == "BM.GPU.A100-v2.8" ] || [ "$shape" == "BM.GPU4.8" ]
then
  mpirun "${inspector_mpirun_args[@]}" "${mpi_args[@]}" \
    --bind-to numa \
    -x NCCL_DEBUG=WARN \
    -x NCCL_IB_SL=0 \
    -x NCCL_IB_TC=41 \
    -x NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
    -x NCCL_IB_GID_INDEX=3 \
    -x NCCL_ALGO=Ring \
    -x NCCL_IB_HCA="${var_NCCL_IB_HCA}" \
    --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --map-by rankfile:file=$RANKFILE  ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50

elif [ "$shape" == "BM.GPU.H100.8" ] || [ "$shape" == "BM.GPU.H200.8" ] || [ "$shape" == "BM.GPU.B200.8" ] || [ "$shape" == "BM.GPU.B300.8" ] || [ "$shape" == "BM.GPU.B300.HS.8" ] || [ "$shape" == "BM.GPU.RTXPRO.8" ]
then
  mpirun "${inspector_mpirun_args[@]}" "${mpi_args[@]}" \
    --bind-to numa \
    -x NCCL_DEBUG=WARN \
    -x NCCL_CUMEM_ENABLE=0 \
    -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
    -x NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
    "${NCCL_ADAPTIVE_ROUTING_ARGS[@]}" \
    -x NCCL_IB_GID_INDEX=3 \
    -x NCCL_IB_TC=41 \
    -x NCCL_IB_SL=0 \
    -x NCCL_IB_TIMEOUT=22 \
    -x NCCL_IGNORE_CPU_AFFINITY=1 \
    -x NCCL_IB_HCA="${var_NCCL_IB_HCA}" \
    "${NCCL_TOPO_ARGS[@]}" \
    --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --map-by rankfile:file=$RANKFILE ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50
elif [[ "$shape" == "BM.GPU.GB200.4" || "$shape" == "BM.GPU.GB200-v2.4" ]]
then
  mpirun "${inspector_mpirun_args[@]}" "${mpi_args[@]}" --bind-to none \
    -x NCCL_DEBUG=WARN \
    -x NCCL_MNNVL_ENABLE=1 \
    -x NCCL_CUMEM_ENABLE=1 \
    -x NCCL_IB_HCA==mlx5_0,mlx5_1,mlx5_3,mlx5_4 \
    -x NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
    -x NCCL_NVLS_ENABLE=1 \
    -x NCCL_NET_GDR_C2C=1 \
    --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --map-by rankfile:file=$RANKFILE ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50
elif [ "$shape" == "BM.GPU.GB300.4" ] && [ "$rdma_planes" -gt 1 ]
then
  mpirun "${inspector_mpirun_args[@]}" "${mpi_args[@]}" --bind-to numa \
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
    -x NCCL_IB_ADAPTIVE_ROUTING=1 \
    -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
    -x NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
    -x NCCL_TOPO_FILE=${NCCL_TOPO_FILE:-/opt/oci-hpc/healthchecks/GB300MP.xml} \
    --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --map-by rankfile:file=$RANKFILE ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50
elif [[ "$shape" == "BM.GPU.GB200-v3.4" ]] || { [[ "$shape" == "BM.GPU.GB300.4" ]] && [[ "$rdma_planes" -le 1 ]]; }
then
  mpirun "${inspector_mpirun_args[@]}" "${mpi_args[@]}" --bind-to numa \
    -x NCCL_DEBUG=WARN \
    -x NCCL_MNNVL_ENABLE=1 \
    -x NCCL_CUMEM_ENABLE=1 \
    -x NCCL_IB_HCA==mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8 \
    -x NCCL_NVLS_ENABLE=1 \
    -x NCCL_NET_GDR_C2C=1 \
    -x NCCL_IB_GID_INDEX=3 \
    -x NCCL_IB_TC=41 \
    -x NCCL_IB_SL=0 \
    -x NCCL_IB_TIMEOUT=22 \
    -x NCCL_BUFFSIZE=16777216 \
    -x NCCL_IB_QPS_PER_CONNECTION="$var_NCCL_IB_QPS_PER_CONNECTION" \
    -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
    -x NCCL_NET_GDR_C2C=1 \
    -x NCCL_DMABUF_ENABLE=1 \
    --np $((SLURM_NNODES*SLURM_NTASKS_PER_NODE)) --map-by rankfile:file=$RANKFILE ${EXEC_CMD} -b 1G -e 16G -f 2 -g 1 -n 50
fi
