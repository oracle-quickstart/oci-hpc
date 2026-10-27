# GPU communication samples

These Slurm jobs and shell scripts exercise multi-node GPU communication.

- `nccl_run_allreduce.sbatch` submits an NVIDIA NCCL all-reduce job through Slurm.
- `nccl_run_allreduce_containers.sbatch` is the container-oriented NCCL variant.
- `nccl_run_allreduce.sh` runs an NCCL all-reduce test against a hostfile, or against compute nodes returned by `mgmt`.
- `rccl_run_allreduce.sbatch` submits an AMD RCCL all-reduce job.

The files include shape-dependent defaults. Adjust Slurm resource requests, partitions, hostfiles, and test parameters for the target cluster. Run communication tests only when the requested nodes are available for validation work.

The NVIDIA NCCL sample accepts `--with-nccl-inspector-jsonl` to write JSONL dumps for collection into MySQL, or `--with-nccl-inspector-otel` to export metrics to Prometheus. Pass the option to `sbatch nccl_run_allreduce.sbatch` or to `nccl_run_allreduce.sh`; omit it to run without the inspector. Existing positional arguments still work, including `nccl_run_allreduce.sh 1 my-hostfile 8 --with-nccl-inspector-jsonl`. These options require the inspector plugin installed on the GPU nodes. For runtimes older than NCCL 2.31.2, the role builds the plugin from the 2.31.2 source without upgrading the runtime. For JSONL retention to remove user-owned dump directories, enable **Sudo Access** (`privilege_sudo=true`) for `cluster_admin_user` on the monitoring host; database rows are still purged if sudo is disabled.

## NCCL image requirements

Use an updated HPC image providing `/opt/oci-hpc/nccl-tests/bin` and an Open MPI
version recorded in `/etc/manifest.yaml` (`verified_components.openmpi.version`).

From the controller, submit the sample with the desired node count:

```sh
sbatch -N2 /opt/oci-hpc/samples/gpu/nccl_run_allreduce.sbatch
```

Look at the end of the job log for bandwidth.

## Network plugin defaults

| Shape                          | RDMA fabric | nccl.conf  | NCCL benchmarks | Single-node HC | Multi-node HC |
| ------------------------------ | ----------- | ---------- | --------------- | -------------- | ------------- |
| A100 (B4.8, A100-v2.8, GPU4.8) | RoCE        | Internal   | Internal        | Internal       | Internal      |
| H100 / H200                    | RoCE        | Internal   | Internal        | Internal       | Internal      |
| B200                           | RoCE        | Internal   | Internal        | Internal       | Internal      |
| RTXPRO                         | RoCE        | Internal   | Internal        | Internal       | Internal      |
| B300 / B300.HS, single-plane   | RoCE        | Internal   | Internal        | Internal       | Internal      |
| B300 / B300.HS, multi-plane    | RoCE        | SPCX       | SPCX            | SPCX           | SPCX          |
| GB200 / GB200-v2               | InfiniBand  | RDMA-SHARP | RDMA-SHARP      | RDMA-SHARP     | RDMA-SHARP    |
| GB200-v3                       | RoCE        | RDMA-SHARP | RDMA-SHARP      | RDMA-SHARP     | RDMA-SHARP    |
| GB300, single-plane            | RoCE        | RDMA-SHARP | RDMA-SHARP      | RDMA-SHARP     | RDMA-SHARP    |
| GB300, multi-plane             | RoCE        | SPCX       | SPCX            | SPCX           | SPCX          |

Internal means NCCL_NET_PLUGIN=none. RDMA-SHARP and Spectrum-X (SPCX) are
the image-provided HPC-X plugins, not HPC-X MPI. The benchmark column applies
to the shell, sbatch and container samples with USE_SPCX unset.

B300/B300.HS multi-plane uses SPCX to keep the plugin policy consistent with
GB300 multi-plane. This is a consistency decision, not a claim that SPCX
is the fastest option for every workload; shape-specific tuning is unchanged.

IMDS rdmaFabricData.planes values 0 and 1 both mean single-plane; values greater
than 1 mean multi-plane and indicate the number of planes.
GB200-v3 keeps its own RoCE HCA mapping, unlike GB200/v2.

USE_SPCX is a benchmark-only override, supported by the shell, sbatch and container
samples. Leave it unset for the defaults above; USE_SPCX=1 selects Spectrum-X NCCL
plugin and USE_SPCX=0 selects Internal even where RDMA-SHARP is the default.
For example: USE_SPCX=0 sbatch nccl_run_allreduce.sbatch

External plugins must resolve to exactly one matching library under /opt/hpcx-*.
Only the selected plugin library directory is added to LD_LIBRARY_PATH; HPC-X MPI
is not initialized. Container runs mount the selected HPC-X package read-only.
The image-built Open MPI remains the launcher. Missing plugins are errors, not
silent fallbacks. Healthchecks do not honor USE_SPCX.

Shape-wide defaults follow the benchmark configuration. Collective- or scale-
specific tuning should stay in the job rather than being added to nccl.conf.
